import pytest

from peruspatial_hub_ogc import merge_crs, parse_wms_layer_catalog
from scripts.build_catalog import deduplicate, inventory_wms, merge_source_refresh

WMS = b'''<WMS_Capabilities xmlns="http://www.opengis.net/wms" version="1.3.0">
<Capability><Layer><Title>Root</Title><CRS>EPSG:4326</CRS>
<Layer><Name>rain</Name><Title>Rainfall</Title><CRS>EPSG:3857</CRS></Layer>
</Layer></Capability></WMS_Capabilities>'''


def test_wms_namespaces_and_crs_inheritance():
    root = parse_wms_layer_catalog(WMS)
    child = root["children"][0]
    assert child["name"] == "rain"
    assert merge_crs(root["crs"], child["crs"]) == ["EPSG:4326", "EPSG:3857"]
    assert merge_crs(["EPSG:4326"], ["EPSG:4326"]) == ["EPSG:4326"]


def test_wms_111_accepts_external_doctype_without_resolving_it():
    payload = b'''<!DOCTYPE WMT_MS_Capabilities SYSTEM "https://unreachable.invalid/wms.dtd">
    <WMT_MS_Capabilities><Capability><Layer><Name>test</Name>
    <SRS>EPSG:4326 EPSG:3857</SRS></Layer></Capability></WMT_MS_Capabilities>'''
    assert parse_wms_layer_catalog(payload)["crs"] == ["EPSG:4326", "EPSG:3857"]


@pytest.mark.parametrize("payload", [b"<html>Login</html>", b"not xml",
    b"<WMS_Capabilities/>", b"<ServiceExceptionReport/>",
    b"<WMS_Capabilities><Capability><Layer/></Capability></WMS_Capabilities>"])
def test_invalid_or_non_importable_wms_is_not_healthy(payload):
    with pytest.raises(ValueError):
        parse_wms_layer_catalog(payload)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_wms_rejects_entity_declarations(encoding):
    payload = '<!DOCTYPE x [<!ENTITY x "value">]><WMS_Capabilities/>'
    with pytest.raises(ValueError, match="entidades"):
        parse_wms_layer_catalog(payload.encode(encoding))


def test_builder_and_runtime_use_same_wms_rules(monkeypatch):
    monkeypatch.setattr("scripts.build_catalog.read_url", lambda *args, **kwargs: WMS)
    source = {"name": "Test", "url": "https://example.test/wms?map=peru", "institution": "Test", "category": "Clima y Riesgos"}
    entries, status = inventory_wms(source)
    assert status["status"] == "ok"
    assert entries[1]["service_url"] == source["url"]
    assert entries[1]["crs_options"] == ["EPSG:4326", "EPSG:3857"]


def test_vendor_parameters_distinguish_wms_services():
    entries = [{"type": "wms_layer", "stype": "wms", "url": f"https://example.test/wms?map={name}",
                "layer_name": "rain"} for name in ("peru", "lima")]
    assert len(deduplicate(entries)) == 2


def test_partial_refresh_preserves_missing_entries_and_marks_them_stale():
    source = {"url": "https://example.test/rest/services"}
    old = {"type": "arcgis_map_layer", "url": source["url"] + "/map/MapServer/0", "name": "Old"}
    previous = {"entries": [old], "generated_at": "2026-07-15"}
    entries, status = merge_source_refresh(previous, [], {"status": "error"}, source, [source], "2026-10-28")
    assert entries[0]["stale"] is True
    assert entries[0]["last_verified_at"] == "2026-07-15"
    assert status["retained_entries"] == 1
    assert status["checked_at"] == "2026-10-28"
    assert "stale" not in old


def test_successful_refresh_does_not_keep_retired_entries():
    source = {"url": "https://example.test/rest/services"}
    previous = {"entries": [{"url": source["url"] + "/retired", "type": "arcgis_service"}]}
    entries, status = merge_source_refresh(previous, [], {"status": "ok"}, source, [source], "now")
    assert entries == []
    assert status["retained_entries"] == 0


def test_fresh_inventory_entry_wins_over_overlapping_stale_source():
    fresh = {"url": "https://example.test/map", "type": "arcgis_service", "name": "Fresh"}
    stale = dict(fresh, stale=True, source_url="https://example.test/longer/source")
    assert deduplicate([stale, fresh]) == [fresh]
    assert deduplicate([fresh, stale]) == [fresh]
