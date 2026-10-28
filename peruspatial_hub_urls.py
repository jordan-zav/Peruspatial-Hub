"""Pure URL helpers used by the PeruSpatial Hub QGIS interface."""

from __future__ import annotations

import urllib.parse


def url_with_json(url: str) -> str:
    """Return an ArcGIS REST URL with ``f=json`` while preserving its query."""
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query["f"] = "json"
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )


def clean_rest_url(url: str) -> str:
    """Remove query, fragment and trailing slash from a REST endpoint."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def append_rest_path(url: str, *segments: object) -> str:
    """Append safely encoded path segments to an ArcGIS REST endpoint."""
    base = clean_rest_url(url)
    encoded = [urllib.parse.quote(str(segment).strip("/"), safe="") for segment in segments]
    return "/".join([base] + encoded)


def service_url(directory_url: str, service_name: str, service_type: str) -> str:
    """Build the service URL returned by an ArcGIS REST directory."""
    base = clean_rest_url(directory_url)
    name_parts = [part for part in str(service_name).split("/") if part]
    path = urllib.parse.unquote(urllib.parse.urlsplit(base).path)
    marker = "/rest/services/"
    if marker in path.lower():
        folder_parts = path[path.lower().index(marker) + len(marker):].strip("/").split("/")
        if [part.casefold() for part in name_parts[:len(folder_parts)]] == [part.casefold() for part in folder_parts]:
            name_parts = name_parts[len(folder_parts):]
    return append_rest_path(base, *name_parts, service_type)


def wms_capabilities_url(url: str) -> str:
    """Build a WMS GetCapabilities URL while preserving vendor parameters."""
    parts = urllib.parse.urlsplit(url)
    query = {key: value for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if key.casefold() not in {"service", "request"}}
    query.update({"service": "WMS", "request": "GetCapabilities"})
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )


def wms_service_url(url: str) -> str:
    """Keep vendor parameters (for example MapServer's map=) in WMS layer URLs."""
    parts = urllib.parse.urlsplit(url)
    protocol_keys = {"service", "request", "version", "layers", "styles", "format",
                     "crs", "srs", "bbox", "width", "height", "transparent"}
    query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if key.casefold() not in protocol_keys]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                   urllib.parse.urlencode(query), ""))
