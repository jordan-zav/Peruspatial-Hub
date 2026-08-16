from urllib.parse import parse_qs, urlsplit

from peruspatial_hub_urls import (
    append_rest_path,
    clean_rest_url,
    service_url,
    url_with_json,
    wms_capabilities_url,
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
