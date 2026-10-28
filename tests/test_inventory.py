import pytest

from peruspatial_hub_catalog import arcgis_directory, arcgis_service_records, arcgis_data_kind, is_psad56_reference
from scripts import build_catalog as builder


SOURCE = {"url": "https://example.test/rest/services", "institution": "Fixture",
          "name": "Fixture", "category": "Geología y Minería", "stype": "arcgis_rest"}
DESCRIPTOR = {"url": SOURCE["url"] + "/Map/MapServer", "service_type": "MapServer",
              "name": "Map", "path": "Fixture / Map"}


@pytest.mark.parametrize("payload", [{"message": "Temporarily unavailable"}, {"folders": None},
    {"services": {}}, {"folders": [None]}, {"services": [{"name": "Bad"}]}])
def test_incomplete_directory_cannot_be_treated_as_an_empty_success(payload):
    with pytest.raises(ValueError):
        arcgis_directory(payload)


def test_valid_empty_directory_is_allowed():
    assert arcgis_directory({"folders": [], "services": []}) == ([], [])


@pytest.mark.parametrize("payload", [{"message": "Login required"}, {"layers": None},
    {"layers": [{"id": True}]}, {"layers": [{"id": -1}]},
    {"layers": [{"id": 0}], "tables": [{"id": 0}]},
    {"layers": [{"id": 0, "parentLayerId": 1}, {"id": 1, "parentLayerId": 0}]}])
def test_invalid_layer_inventories_do_not_silently_drop_or_merge_resources(payload):
    with pytest.raises(ValueError):
        arcgis_service_records(payload, "MapServer")


def test_incomplete_service_response_retains_old_layer_and_service_metadata(monkeypatch):
    def fetch(url):
        if url == SOURCE["url"]:
            return {"folders": [], "services": [{"name": "Map", "type": "MapServer"}]}
        return {"message": "Temporarily unavailable"}
    monkeypatch.setattr(builder, "fetch_json", fetch)
    old_service = builder.arcgis_service_entry(SOURCE, DESCRIPTOR)
    old_service.update(last_verified_at="old-service-check", capabilities="Map,Query")
    old_layer = dict(old_service, type="arcgis_map_layer", layer_id=0, url=DESCRIPTOR["url"] + "/0")
    fresh, status = builder.inventory_arcgis(SOURCE)
    assert status["status"] == "partial"
    merged, _ = builder.merge_source_refresh({"entries": [old_service, old_layer]}, fresh, status,
                                             SOURCE, [SOURCE], "new-check")
    service = next(entry for entry in merged if entry["type"] == "arcgis_service")
    leaf = next(entry for entry in merged if entry.get("layer_id") == 0)
    assert service["stale"] and service["last_verified_at"] == "old-service-check"
    assert service["capabilities"] == "Map,Query"
    assert leaf["stale"] and leaf["last_verified_at"] == "old-service-check"


def test_image_service_is_actually_checked_before_marking_verified(monkeypatch):
    def fetch(url):
        if url == SOURCE["url"]:
            return {"services": [{"name": "Image", "type": "ImageServer"}]}
        return {"description": "Not an image service"}
    monkeypatch.setattr(builder, "fetch_json", fetch)
    entries, status = builder.inventory_arcgis(SOURCE)
    assert status["status"] == "partial"
    assert len(entries) == 1 and entries[0]["stale"]


def test_detail_preserves_tables_geometry_crs_and_group_search_context():
    metadata = {"spatialReference": {"wkid": 32718}, "layers": [
        {"id": 10, "name": "Riesgos", "type": "Group Layer", "parentLayerId": -1, "subLayerIds": [0]},
        {"id": 0, "name": "Zonas", "parentLayerId": 10}],
        "tables": [{"id": 20, "name": "Referencias"}]}
    detail = {0: {"id": 0, "name": "Zonas", "type": "Feature Layer", "geometryType": "esriGeometryPolygon",
                  "fields": [{"name": "OBJECTID"}, {"name": "CODIGO"}], "capabilities": "Map,Query"},
              20: {"id": 20, "name": "Referencias", "type": "Table", "fields": [{"name": "OBJECTID"}]}}
    entries = builder.arcgis_layer_entries(SOURCE, DESCRIPTOR, metadata, detail)
    layer = next(entry for entry in entries if entry["layer_id"] == 0)
    table = next(entry for entry in entries if entry["layer_id"] == 20)
    assert len(entries) == 2
    assert layer["type"] == "arcgis_map_layer"  # Keep rendered fallback for MapServer vectors.
    assert layer["data_kind"] == "vectorial" and layer["geometry_type"] == "esriGeometryPolygon"
    assert layer["spatial_reference"] == {"wkid": 32718} and layer["field_count"] == 2
    assert layer["path"] == "Fixture / Map / Riesgos / Zonas"
    assert layer["metadata_level"] == "layer"
    assert table["is_table"] and table["data_kind"] == "tabla" and table["display_type"] == "Tabla REST"
    assert "spatial_reference" not in table and "extent" not in table


def test_incomplete_detail_does_not_claim_a_known_field_schema():
    entries = builder.arcgis_layer_entries(SOURCE, DESCRIPTOR, {"layers": [{"id": 0, "name": "Summary"}]})
    assert entries[0]["metadata_level"] == "service_listing"
    assert "field_count" not in entries[0]


def test_retained_entry_uses_source_check_not_newer_unrelated_catalog_date():
    old = {"type": "arcgis_map_layer", "url": DESCRIPTOR["url"] + "/0"}
    previous = {"entries": [old], "generated_at": "newer-other-source-refresh",
                "sources": [{"url": SOURCE["url"], "checked_at": "actual-source-check"}]}
    entries, _ = builder.merge_source_refresh(previous, [], {"status": "error"}, SOURCE, [SOURCE], "now")
    assert entries[0]["last_verified_at"] == "actual-source-check"


def test_fresh_entry_records_its_own_verification_date():
    entry = builder.arcgis_service_entry(SOURCE, DESCRIPTOR)
    entries, _ = builder.merge_source_refresh({}, [entry], {"status": "ok"}, SOURCE, [SOURCE], "checked-now")
    assert entries[0]["last_verified_at"] == "checked-now"


@pytest.mark.parametrize("record,expected", [
    ({"type": "Feature Layer"}, "vectorial"),
    ({"type": "Raster Layer"}, "raster"),
    ({"type": "Table"}, "tabla"),
    ({"type": "Subtype Group Layer", "subLayers": [{"id": 1}]}, "grupo"),
    ({"type": "Group Layer", "subLayerIds": []}, "grupo"),
    ({"geometryType": "esriGeometryPoint"}, "vectorial"),
    ({}, "mixto"),
])
def test_classification_uses_declared_type_even_without_geometry_in_summary(record, expected):
    assert arcgis_data_kind(record) == expected


def test_unrelated_private_folder_does_not_keep_retired_layers_of_verified_service():
    old = {"type": "arcgis_map_layer", "url": DESCRIPTOR["url"] + "/6",
           "service_url": DESCRIPTOR["url"], "layer_id": 6, "name": "Old thematic layer"}
    status = {"status": "partial", "verified_services": [DESCRIPTOR["url"]]}
    entries, result = builder.merge_source_refresh({"entries": [old]}, [], status, SOURCE, [SOURCE], "now")
    assert entries == [] and result["retained_entries"] == 0


def test_partial_public_directory_does_not_prove_an_old_private_service_is_gone():
    old = {"type": "arcgis_service", "url": DESCRIPTOR["url"], "name": "Gone"}
    status = {"status": "partial", "verified_directories": [SOURCE["url"]]}
    entries, _ = builder.merge_source_refresh({"entries": [old]}, [], status, SOURCE, [SOURCE], "now")
    assert len(entries) == 1 and entries[0]["stale"]
    entries, _ = builder.merge_source_refresh({"entries": [old]}, [], {"status": "partial"}, SOURCE, [SOURCE], "now")
    assert len(entries) == 1 and entries[0]["stale"]


@pytest.mark.parametrize("reference,expected", [
    ({"wkid": 4248}, True), ({"wkid": 4326}, False),
    ({"wkt": 'GEOGCS["PSAD56",DATUM["Provisional_South_American_Datum_1956"]]'}, True),
    (None, False),
])
def test_datum_warning_uses_declared_reference_not_institution_alone(reference, expected):
    assert is_psad56_reference(reference) is expected


def test_spatial_psad56_gets_warning_but_nonspatial_table_does_not_inherit_crs():
    metadata = {"spatialReference": {"wkid": 4248}}
    vector = builder.layer_metadata_fields({"type": "Feature Layer"}, metadata)
    table = builder.layer_metadata_fields({"type": "Table", "fields": []}, metadata, is_table=True)
    assert vector["crs_warning"] and vector["spatial_reference"] == {"wkid": 4248}
    assert "spatial_reference" not in table and not table.get("crs_warning")


def test_bulk_metadata_falls_back_to_individual_layers_without_marking_inventory_incomplete(monkeypatch):
    def fetch(url):
        if url == DESCRIPTOR["url"]:
            return {"layers": [{"id": 0, "name": "Leaf", "parentLayerId": -1}]}
        if url.endswith("/layers"):
            raise RuntimeError("Bulk resource unavailable")
        return {"id": 0, "name": "Leaf", "type": "Feature Layer", "fields": [{"name": "ID"}]}
    monkeypatch.setattr(builder, "fetch_json", fetch)
    entries, warnings = builder.inventory_arcgis_service(SOURCE, DESCRIPTOR)
    assert not warnings and entries[0]["metadata_bulk_fallback"]
    assert entries[1]["metadata_level"] == "layer" and entries[1]["field_count"] == 1
