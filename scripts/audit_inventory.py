"""Snapshot official metadata and compare every inventoried REST/WMS resource."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import build_catalog as builder
from peruspatial_hub_sources import LIVE_SERVERS
from peruspatial_hub_catalog import arcgis_data_kind, resolve_arcgis_inventory
from peruspatial_hub_urls import append_rest_path, clean_rest_url


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".new")
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


class MetadataSnapshot:
    """Cache bounded metadata responses; limit load globally and per host."""

    def __init__(self, output, offline=False):
        self.cache = output / "responses"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        run_path = output / "snapshot.json"
        if run_path.is_file():
            self.started_at = json.loads(run_path.read_text(encoding="utf-8"))["started_at"]
        else:
            dates = [json.loads(path.read_text(encoding="utf-8")).get("checked_at") for path in self.cache.glob("*.json")]
            self.started_at = min((value for value in dates if value), default=datetime.now(timezone.utc).isoformat())
            write_json(run_path, {"started_at": self.started_at})
        self.lock = threading.Lock()
        self.global_limit = threading.BoundedSemaphore(8)
        self.host_limits = defaultdict(lambda: threading.BoundedSemaphore(2))
        self.url_locks = defaultdict(threading.Lock)

    def read(self, url, accept, timeout=15, attempts=2):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("Metadata audit requires a public HTTPS URL without credentials")
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        body_path, info_path = self.cache / (key + ".body"), self.cache / (key + ".json")
        with self.lock:
            url_lock, host_limit = self.url_locks[key], self.host_limits[parts.hostname]
        with url_lock:
            if info_path.is_file():
                info = json.loads(info_path.read_text(encoding="utf-8"))
                if info.get("ok"):
                    return body_path.read_bytes()
                raise RuntimeError(f"{url}: {info.get('error', 'cached metadata failure')}")
            if self.offline:
                raise RuntimeError(f"No snapshot response for {url}")
            started = time.monotonic()
            info = {"url": url, "checked_at": datetime.now(timezone.utc).isoformat()}
            last_error = None
            with self.global_limit, host_limit:
                for attempt in range(attempts):
                    try:
                        request = urllib.request.Request(url, headers={
                            "User-Agent": "PeruSpatial-Hub-Inventory-Audit/1.0", "Accept": accept})
                        with urllib.request.urlopen(request, timeout=timeout) as response:
                            body = response.read(builder.MAX_RESPONSE_BYTES + 1)
                            if len(body) > builder.MAX_RESPONSE_BYTES:
                                raise ValueError("Metadata response exceeds 25 MiB")
                            info.update(ok=True, status=response.status, response_url=response.url,
                                        bytes=len(body), attempts=attempt + 1)
                        body_path.write_bytes(body)
                        break
                    except Exception as exc:
                        last_error = exc
                        info.update(ok=False, error=str(exc), attempts=attempt + 1)
                        if isinstance(exc, urllib.error.HTTPError):
                            info["status"] = exc.code
                            if exc.code not in {429, 500, 502, 503, 504}:
                                break
                        if attempt + 1 < attempts:
                            time.sleep(0.5)
            info["seconds"] = round(time.monotonic() - started, 3)
            write_json(info_path, info)
            if not info["ok"]:
                raise RuntimeError(f"{url}: {last_error}")
            return body


def audit_local(catalog):
    issues = []
    known_sources = {source["url"]: source for source in LIVE_SERVERS}
    seen = set()
    for index, entry in enumerate(catalog.get("entries", [])):
        reasons = []
        key = builder.entry_key(entry)
        if key in seen:
            reasons.append("duplicate_resource")
        seen.add(key)
        source_url = builder.entry_source(entry, LIVE_SERVERS)
        source = known_sources.get(source_url)
        if source is None:
            reasons.append("unknown_source")
        elif (entry.get("institution"), entry.get("category")) != (source["institution"], source["category"]):
            reasons.append("source_attribution_mismatch")
        parts = urllib.parse.urlsplit(entry.get("url", ""))
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            reasons.append("invalid_https_endpoint")
        if entry.get("type") in {"arcgis_vector_layer", "arcgis_map_layer"}:
            layer_id = entry.get("layer_id")
            if type(layer_id) is not int or layer_id < 0:
                reasons.append("invalid_layer_id")
            elif clean_rest_url(entry["url"]) != append_rest_path(entry.get("service_url", ""), layer_id):
                reasons.append("layer_endpoint_mismatch")
        if entry.get("type") == "wms_layer":
            if not entry.get("layer_name"):
                reasons.append("missing_wms_name")
            if not entry.get("crs_options"):
                reasons.append("missing_wms_crs")
        if reasons:
            issues.append({"index": index, "url": entry.get("url"), "name": entry.get("name"), "issues": reasons})
    return {"entries": len(catalog.get("entries", [])),
            "types": dict(Counter(entry.get("type") for entry in catalog.get("entries", []))),
            "stale": sum(bool(entry.get("stale")) for entry in catalog.get("entries", [])),
            "issues": issues}


def compact_layer(metadata, is_table=False):
    extent = metadata.get("extent") or {}
    fields = metadata.get("fields") or []
    result = {key: metadata[key] for key in (
        "id", "name", "type", "geometryType", "parentLayerId", "subLayerIds", "capabilities",
        "minScale", "maxScale", "objectIdField", "objectIdFieldName", "spatialReference",
        "bandCount", "pixelType", "pixelSizeX", "pixelSizeY", "supportsStatistics") if key in metadata}
    result.update(is_table=is_table, extent=extent, field_count=len(fields),
        fields=[{key: field[key] for key in ("name", "type", "alias", "length", "nullable") if key in field}
                for field in fields if isinstance(field, dict)])
    result["issues"] = sorted(set(metadata.get("metadata_warnings") or []))
    names = [field.get("name") for field in fields if isinstance(field, dict)]
    if len(names) != len(set(names)):
        result["issues"].append("duplicate_field_names")
    oid = metadata.get("objectIdField") or metadata.get("objectIdFieldName")
    if oid and fields and oid not in names:
        result["issues"].append("object_id_field_missing_from_schema")
    if extent and all(key in extent for key in ("xmin", "ymin", "xmax", "ymax")):
        if extent["xmin"] > extent["xmax"] or extent["ymin"] > extent["ymax"]:
            result["issues"].append("inverted_extent")
    return result


def audit_rest_service(url, entries):
    result = {"url": url, "institution": entries[0].get("institution"), "layers": [], "errors": []}
    try:
        root = builder.fetch_json(url)
        kind = "ImageServer" if url.endswith("/ImageServer") else "FeatureServer" if url.endswith("/FeatureServer") else "MapServer"
        root = resolve_arcgis_inventory(root, kind, lambda part: builder.fetch_json(append_rest_path(url, part)))
        result["service_metadata"] = {key: root[key] for key in (
            "currentVersion", "serviceDescription", "capabilities", "supportedQueryFormats",
            "spatialReference", "fullExtent", "initialExtent", "maxRecordCount") if key in root}
        if url.endswith("/ImageServer"):
            result["image"] = compact_layer(root)
            result["status"] = "ok" if "bandCount" in root or "pixelType" in root else "invalid_image_metadata"
            return result
        result["errors"].extend({"error": error} for error in root["_inventory_errors"])
        remote_ids = set()
        for table, key in ((False, "layers"), (True, "tables")):
            for summary in root.get(key, []):
                layer_id = summary.get("id")
                if layer_id is None:
                    continue
                remote_ids.add(layer_id)
                metadata = summary
                if metadata is None or not any(field in metadata for field in ("fields", "extent", "subLayers", "subLayerIds")):
                    try:
                        metadata = builder.fetch_json(append_rest_path(url, layer_id))
                    except Exception as exc:
                        result["errors"].append({"layer_id": layer_id, "error": str(exc)})
                        continue
                result["layers"].append(compact_layer(metadata, table))
        local_ids = {entry["layer_id"] for entry in entries if "layer_id" in entry}
        result["local_ids_absent_from_service"] = sorted(local_ids - remote_ids)
        result["inventory_complete"] = root["_inventory_complete"] and not result["errors"]
        result["status"] = "partial" if result["errors"] else "ok"
    except Exception as exc:
        result.update(status="invalid_metadata" if isinstance(exc, ValueError) else "unavailable", error=str(exc))
    return result


def export_metadata(output, services, catalog):
    columns = ["institution", "service_url", "layer_id", "name", "type", "is_table", "geometry_type",
               "wkid", "latest_wkid", "field_count", "capabilities", "issues"]
    with (output / "layer-metadata.csv").open("w", encoding="utf-8-sig", newline="") as target, \
            (output / "field-schemas.csv").open("w", encoding="utf-8-sig", newline="") as schemas:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        field_writer = csv.DictWriter(schemas, fieldnames=["service_url", "layer_id", "name", "type", "alias", "length", "nullable"])
        field_writer.writeheader()
        for service in sorted(services, key=lambda item: item["url"]):
            for layer in service["layers"] + ([service["image"]] if "image" in service else []):
                sr = (layer.get("extent") or {}).get("spatialReference") or layer.get("spatialReference") or service.get("service_metadata", {}).get("spatialReference") or {}
                writer.writerow({"institution": service["institution"], "service_url": service["url"],
                    "layer_id": layer.get("id", ""), "name": layer.get("name", ""), "type": layer.get("type", "ImageServer"),
                    "is_table": layer.get("is_table"), "geometry_type": layer.get("geometryType", ""),
                    "wkid": sr.get("wkid", ""), "latest_wkid": sr.get("latestWkid", ""),
                    "field_count": layer["field_count"], "capabilities": layer.get("capabilities", ""), "issues": ";".join(layer["issues"])})
                for field in layer["fields"]:
                    field_writer.writerow({"service_url": service["url"], "layer_id": layer.get("id", ""), **field})
        for entry in catalog["entries"]:
            if entry.get("type") == "wms_layer":
                writer.writerow({"institution": entry["institution"], "service_url": entry["service_url"],
                    "layer_id": entry["layer_name"], "name": entry["name"], "type": "WMS", "issues": "stale" if entry.get("stale") else ""})


def compare_inventory(before, after, services):
    old = {builder.entry_key(entry): entry for entry in before["entries"]}
    new = {builder.entry_key(entry): entry for entry in after["entries"]}
    service_index = {item["url"]: item for item in services}
    confirmed_missing, unverified, names_differ, repurposed = [], [], [], []
    for entry in before["entries"]:
        if "layer_id" not in entry:
            continue
        url = clean_rest_url(entry.get("service_url", ""))
        service = service_index.get(url)
        if service is None or service["status"] not in {"ok", "partial"}:
            unverified.append({"url": entry["url"], "name": entry["name"]})
            continue
        remote = {layer.get("id"): layer for layer in service["layers"]}
        layer = remote.get(entry["layer_id"])
        if layer is None:
            target = confirmed_missing if service.get("inventory_complete", True) else unverified
            target.append({"url": entry["url"], "name": entry["name"]})
        elif arcgis_data_kind(layer) == "grupo":
            repurposed.append({"url": entry["url"], "old": entry["name"], "published_group": layer.get("name")})
        elif entry["name"] != layer.get("name"):
            names_differ.append({"url": entry["url"], "old": entry["name"], "published": layer.get("name")})
    common = old.keys() & new.keys()
    return {"before_entries": len(old), "after_entries": len(new),
        "added_resources": [{"url": new[key]["url"], "name": new[key]["name"]} for key in new.keys() - old.keys()],
        "removed_resources": [{"url": old[key]["url"], "name": old[key]["name"]} for key in old.keys() - new.keys()],
        "confirmed_missing_layer_ids": confirmed_missing, "unverified_old_layers": unverified,
        "repurposed_layer_ids": repurposed,
        "published_name_differences": names_differ,
        "updated_display_types": sum(old[key].get("display_type") != new[key].get("display_type") for key in common),
        "updated_group_paths": sum(old[key].get("path") != new[key].get("path") for key in common),
        "entries_with_field_counts": sum("field_count" in entry for entry in after["entries"]),
        "entries_with_geometry_types": sum(bool(entry.get("geometry_type")) for entry in after["entries"]),
        "entries_with_crs_metadata": sum(bool(entry.get("spatial_reference")) for entry in after["entries"]),
        "entries_with_metadata_warnings": sum(bool(entry.get("metadata_warnings")) for entry in after["entries"]),
        "entries_with_duplicate_fields": sum("duplicate_field_names" in entry.get("metadata_warnings", []) for entry in after["entries"]),
        "stale_entries": sum(bool(entry.get("stale")) for entry in after["entries"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "catalog/catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true", help="Re-analyse saved responses without HTTP requests")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    previous = json.loads(args.catalog.read_text(encoding="utf-8"))
    local = audit_local(previous)
    write_json(args.output / "local-audit.json", local)
    print(f"Local inventory: {local['entries']} entries; {len(local['issues'])} entries with structural issues", flush=True)
    snapshot = MetadataSnapshot(args.output, args.offline)
    builder.read_url = snapshot.read
    refreshed = builder.build_catalog(previous=previous, verified_at=snapshot.started_at)
    write_json(args.output / "catalog-refreshed.json", refreshed)
    groups = defaultdict(list)
    for entry in previous["entries"] + refreshed["entries"]:
        if entry.get("stype") != "wms":
            groups[clean_rest_url(entry.get("service_url") or entry["url"])].append(entry)
    print(f"Inspecting full metadata for {len(groups)} REST services", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(audit_rest_service, url, entries): url for url, entries in groups.items()}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            key = hashlib.sha256(result["url"].encode("utf-8")).hexdigest()
            write_json(args.output / "services" / (key + ".json"), result)
            if len(results) % 25 == 0 or result["status"] != "ok":
                print(f"Service metadata {len(results)}/{len(groups)}: {result['status']} {result['url']}", flush=True)
            write_json(args.output / "progress.json", {"services_done": len(results), "services_total": len(groups),
                "statuses": dict(Counter(item["status"] for item in results))})
    summary = {"snapshot_started_at": snapshot.started_at, "analysed_at": datetime.now(timezone.utc).isoformat(), "local": local,
        "refreshed_entries": refreshed["entry_count"], "sources": refreshed["sources"],
        "services": len(results), "service_statuses": dict(Counter(item["status"] for item in results)),
        "unavailable_services": [{key: item[key] for key in ("url", "institution", "status", "error") if key in item}
                                 for item in results if item["status"] not in {"ok", "partial"}],
        "incomplete_service_hierarchies": [{"url": item["url"], "errors": item["errors"]}
                                          for item in results if item["status"] == "partial"],
        "layer_metadata_records": sum(len(item["layers"]) for item in results),
        "image_metadata_records": sum("image" in item for item in results),
        "field_metadata_records": sum(layer["field_count"] for item in results
                                      for layer in item["layers"] + ([item["image"]] if "image" in item else [])),
        "layer_schema_issues": [{"url": item["url"], "id": layer.get("id"), "issues": layer["issues"]}
                                for item in results for layer in item["layers"] if layer["issues"]]}
    write_json(args.output / "summary.json", summary)
    export_metadata(args.output, results, refreshed)
    write_json(args.output / "comparison.json", compare_inventory(previous, refreshed, results))
    print(json.dumps({key: value for key, value in summary.items() if key not in {"local", "sources", "layer_schema_issues"}}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
