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
    current_folder = urllib.parse.unquote(urllib.parse.urlsplit(base).path.rstrip("/").split("/")[-1])
    if len(name_parts) > 1 and name_parts[0].lower() == current_folder.lower():
        name_parts = name_parts[1:]
    return append_rest_path(base, *name_parts, service_type)


def wms_capabilities_url(url: str) -> str:
    """Build a WMS GetCapabilities URL while preserving vendor parameters."""
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query.update({"service": "WMS", "request": "GetCapabilities"})
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )
