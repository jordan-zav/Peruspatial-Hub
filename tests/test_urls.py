from urllib.parse import parse_qs, urlsplit

from peruspatial_hub_urls import (
    append_rest_path,
    clean_rest_url,
    favorite_identity,
    service_url,
    url_with_json,
    wms_capabilities_url,
    wms_service_url,
)


def test_url_with_json_preserves_existing_query():
    result = url_with_json("https://example.test/rest/services?token=public")
    assert parse_qs(urlsplit(result).query) == {"token": ["public"], "f": ["json"]}


def test_clean_and_append_rest_path():
    endpoint = "https://example.test/rest/services/?f=json#section"
    assert clean_rest_url(endpoint) == "https://example.test/rest/services"
    assert append_rest_path(endpoint, "Geología histórica", 4).endswith(
        "/Geolog%C3%ADa%20hist%C3%B3rica/4"
    )


def test_service_url_avoids_duplicate_current_folder():
    result = service_url(
        "https://example.test/rest/services/Geologia",
        "Geologia/Mapa Nacional",
        "MapServer",
    )
    assert result == "https://example.test/rest/services/Geologia/Mapa%20Nacional/MapServer"


def test_wms_capabilities_preserves_vendor_parameters():
    result = wms_capabilities_url("https://example.test/wms?map=peru")
    assert parse_qs(urlsplit(result).query) == {
        "map": ["peru"],
        "service": ["WMS"],
        "request": ["GetCapabilities"],
    }


def test_nested_arcgis_folders_do_not_repeat_full_service_path():
    assert service_url("https://example.test/rest/services/A/B", "A/B/Mapa", "MapServer") == "https://example.test/rest/services/A/B/Mapa/MapServer"


def test_wms_kvp_keys_are_case_insensitive():
    query = parse_qs(urlsplit(wms_capabilities_url("https://example.test/wms?SERVICE=wms&REQUEST=GetMap&map=peru")).query)
    assert query == {"map": ["peru"], "service": ["WMS"], "request": ["GetCapabilities"]}


def test_wms_service_keeps_vendor_map_but_removes_request_specific_parameters():
    assert wms_service_url("https://example.test/wms?map=peru&SERVICE=WMS&request=GetMap&BBOX=0,0,1,1") == "https://example.test/wms?map=peru"


def test_favorites_distinguish_named_wms_layers_and_vendor_maps():
    entry = {"type": "wms_layer", "name": "Same title", "url": "https://example.test/wms?map=peru", "layer_name": "one"}
    assert favorite_identity(entry) != favorite_identity(dict(entry, layer_name="two"))
    assert favorite_identity(entry) != favorite_identity(dict(entry, url="https://example.test/wms?map=world"))
    assert favorite_identity(entry) == favorite_identity(dict(entry, name="Renamed"))


def test_favorites_deduplicate_rest_aliases_without_merging_different_layers():
    entry = {"type": "arcgis_vector_layer", "name": "Original", "url": "https://example.test/rest/FeatureServer/0"}
    assert favorite_identity(entry) == favorite_identity(dict(entry, name="Alias", layer_id=0))
    assert favorite_identity(entry) != favorite_identity(dict(entry, url="https://example.test/rest/FeatureServer/1"))
