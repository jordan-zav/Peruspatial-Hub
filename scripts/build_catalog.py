"""Build the offline PeruSpatial Hub inventory from official REST/WMS roots."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from peruspatial_hub_catalog import CATALOG_SCHEMA_VERSION, normalize_search_text
from peruspatial_hub_ogc import merge_crs, parse_wms_layer_catalog
from peruspatial_hub_sources import LIVE_SERVERS
from peruspatial_hub_urls import (
    append_rest_path,
    clean_rest_url,
    service_url,
    url_with_json,
    wms_capabilities_url,
    wms_service_url,
)


USER_AGENT = "PeruSpatial-Hub-Catalog-Builder/1.2"
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
MAX_DIRECTORIES_PER_SOURCE = 500


def read_url(url, accept, timeout=15, attempts=2):
    """Read one public endpoint with bounded retries and response size."""
    last_error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": accept},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise RuntimeError("response exceeded the size limit")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.4)
    raise RuntimeError(f"{url}: {last_error}")


def fetch_json(url):
    payload = read_url(url_with_json(url), "application/json")
    data = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("ArcGIS response is not an object")
    if data.get("error"):
        error = data["error"]
        raise RuntimeError(f"ArcGIS {error.get('code', '')}: {error.get('message', 'error')}")
    return data


def display_type(service_type):
    return {
        "MapServer": "Servicio REST",
        "FeatureServer": "Servicio vectorial REST",
        "ImageServer": "Raster REST",
    }.get(service_type, service_type)


def service_stype(service_type):
    return {
        "MapServer": "arcgis_mapserver",
        "FeatureServer": "arcgisfeatureserver",
        "ImageServer": "arcgis_imageserver",
    }[service_type]


def finalize_entry(entry):
    # Search text is precomputed once when the plugin loads the inventory. It is
    # intentionally omitted from JSON to keep the bundled catalog compact.
    return entry


def arcgis_service_entry(source, descriptor):
    service_type = descriptor["service_type"]
    is_image = service_type == "ImageServer"
    entry = {
        "type": "arcgis_raster_layer" if is_image else "arcgis_service",
        "stype": service_stype(service_type),
        "service_kind": service_type,
        "url": descriptor["url"],
        "service_url": descriptor["url"],
        "name": descriptor["name"],
        "institution": source["institution"],
        "category": source["category"],
        "description": f"Servicio {service_type} inventariado de {source['institution']}.",
        "display_type": display_type(service_type),
        "path": descriptor["path"],
        "crs_warning": source.get("crs_warning", False),
        "is_loaded": is_image,
    }
    return finalize_entry(entry)


def arcgis_layer_entries(source, descriptor):
    service_type = descriptor["service_type"]
    if service_type == "ImageServer":
        return []

    metadata = fetch_json(descriptor["url"])
    records = []
    for layer in metadata.get("layers", []):
        record = dict(layer)
        record["is_table"] = False
        records.append(record)
    for table in metadata.get("tables", []):
        record = dict(table)
        record["is_table"] = True
        records.append(record)

    entries = []
    stype = service_stype(service_type)
    for record in records:
        layer_id = record.get("id")
        if layer_id is None:
            continue
        if record.get("type") == "Group Layer" or record.get("subLayerIds"):
            continue

        name = record.get("name") or f"Capa {layer_id}"
        layer_type = (
            "arcgis_vector_layer"
            if service_type == "FeatureServer" or record.get("is_table")
            else "arcgis_map_layer"
        )
        layer_url = append_rest_path(descriptor["url"], layer_id)
        entry = {
            "type": layer_type,
            "stype": stype,
            "service_kind": service_type,
            "url": layer_url,
            "service_url": descriptor["url"],
            "layer_id": layer_id,
            "name": name,
            "institution": source["institution"],
            "category": source["category"],
            "description": f"Capa {layer_id} del servicio ArcGIS REST {service_type}.",
            "display_type": "Vectorial REST" if layer_type == "arcgis_vector_layer" else "Capa REST",
            "path": f"{descriptor['path']} / {name}",
            "crs_warning": source.get("crs_warning", False),
            "is_loaded": True,
        }
        entries.append(finalize_entry(entry))
    return entries


def discover_arcgis_services(source):
    queue = [clean_rest_url(source["url"])]
    visited = set()
    services = {}
    errors = []

    while queue and len(visited) < MAX_DIRECTORIES_PER_SOURCE:
        directory_url = queue.pop(0)
        if directory_url in visited:
            continue
        visited.add(directory_url)
        try:
            data = fetch_json(directory_url)
        except Exception as exc:
            errors.append(str(exc))
            continue

        for folder in data.get("folders", []):
            child_url = append_rest_path(directory_url, folder)
            if child_url not in visited:
                queue.append(child_url)

        for service in data.get("services", []):
            name = service.get("name")
            service_type = service.get("type")
            if not name or service_type not in {"MapServer", "FeatureServer", "ImageServer"}:
                continue
            url = service_url(directory_url, name, service_type)
            short_name = str(name).split("/")[-1]
            services[url] = {
                "url": url,
                "name": short_name,
                "service_type": service_type,
                "path": f"{source['institution']} / {name}",
            }

    if queue:
        errors.append(f"directory limit reached ({MAX_DIRECTORIES_PER_SOURCE})")
    return list(services.values()), errors, len(visited)


def inventory_arcgis(source):
    descriptors, errors, directory_count = discover_arcgis_services(source)
    entries = [arcgis_service_entry(source, descriptor) for descriptor in descriptors]

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(arcgis_layer_entries, source, descriptor): descriptor
            for descriptor in descriptors
            if descriptor["service_type"] != "ImageServer"
        }
        for future in as_completed(future_map):
            try:
                entries.extend(future.result())
            except Exception as exc:
                errors.append(str(exc))

    return entries, {
        "institution": source["institution"],
        "name": source["name"],
        "url": source["url"],
        "type": "arcgis_rest",
        "directories": directory_count,
        "entries": len(entries),
        "status": "ok" if not errors else ("partial" if entries else "error"),
        "errors": errors[:20],
    }


def local_name(tag):
    return str(tag).rsplit("}", 1)[-1]


def direct_children(element, name):
    return [child for child in list(element) if local_name(child.tag) == name]


def direct_text(element, name):
    children = direct_children(element, name)
    return (children[0].text or "").strip() if children else ""


def inventory_wms(source):
    entries = [{
        "type": "ogc_service", "stype": "wms", "url": source["url"],
        "service_url": wms_service_url(source["url"]),
        "name": source["name"], "institution": source["institution"],
        "category": source["category"], "description": f"Servicio WMS de {source['institution']}.",
        "display_type": "Servicio WMS", "path": f"{source['institution']} / {source['name']}",
        "is_loaded": False,
    }]
    errors = []
    try:
        payload = read_url(wms_capabilities_url(source["url"]), "application/xml,text/xml", timeout=30)
        root_layer = parse_wms_layer_catalog(payload)

        def walk(layer, inherited, path):
            crs = merge_crs(inherited, layer["crs"])
            title = layer["title"] or "Capa WMS"
            layer_name = layer["name"]
            current_path = f"{path} / {title}"
            if layer_name:
                entries.append({
                    "type": "wms_layer", "stype": "wms", "url": source["url"],
                    "service_url": wms_service_url(source["url"]),
                    "layer_name": layer_name, "name": title,
                    "institution": source["institution"], "category": source["category"],
                    "crs_options": crs, "description": f"Capa WMS de {source['institution']}.",
                    "display_type": "Capa WMS", "path": current_path, "is_loaded": True,
                })
            for child in layer["children"]:
                walk(child, crs, current_path)

        walk(root_layer, [], source["institution"])
    except Exception as exc:
        errors.append(str(exc))
    return entries, {
        "institution": source["institution"], "name": source["name"], "url": source["url"],
        "type": "wms", "entries": len(entries),
        "status": "ok" if not errors else "error", "errors": errors,
    }


def inventory_source(source):
    try:
        if source["stype"] == "arcgis_rest":
            return inventory_arcgis(source)
        return inventory_wms(source)
    except Exception as exc:
        return [], {
            "institution": source["institution"],
            "name": source["name"],
            "url": source["url"],
            "type": source["stype"],
            "entries": 0,
            "status": "error",
            "errors": [str(exc)],
        }


def entry_key(entry):
    url = (wms_service_url(entry.get("url", "")) if entry.get("stype") == "wms"
           else clean_rest_url(entry.get("url", "")))
    return entry.get("type"), url, entry.get("layer_id"), entry.get("layer_name")


def deduplicate(entries):
    unique = {}
    for entry in entries:
        key = entry_key(entry)
        old = unique.get(key)
        # A fresh response wins over retained metadata. Prefer a more specific
        # source root when the same service appears in overlapping directories.
        def priority(item):
            return bool(item.get("stale")), -len(item.get("source_url", ""))
        if old is None or priority(entry) < priority(old):
            unique[key] = entry
    return sorted(unique.values(), key=lambda item: (
        normalize_search_text(item.get("institution")), normalize_search_text(item.get("name")),
        str(item.get("url", "")),
    ))


def entry_source(entry, sources):
    if entry.get("source_url"):
        return entry["source_url"]
    url = clean_rest_url(entry.get("service_url") or entry.get("url", ""))
    matches = [source["url"] for source in sources
               if url == clean_rest_url(source["url"])
               or url.startswith(clean_rest_url(source["url"]) + "/")]
    return max(matches, key=len) if matches else None


def merge_source_refresh(previous, fresh, status, source, all_sources, verified_at):
    fresh = [dict(entry, source_url=source["url"]) for entry in fresh]
    fresh_keys = {entry_key(entry) for entry in fresh}
    retained = []
    if status["status"] != "ok":
        for old in previous.get("entries", []):
            if entry_source(old, all_sources) == source["url"] and entry_key(old) not in fresh_keys:
                entry = {key: value for key, value in old.items() if not key.startswith("_")}
                entry.update(source_url=source["url"], stale=True,
                             last_verified_at=old.get("last_verified_at", previous.get("generated_at")))
                retained.append(entry)
    status = dict(status, checked_at=verified_at, retained_entries=len(retained),
                  entries=len(fresh) + len(retained))
    return retained + fresh, status


def build_catalog(sources=None, previous=None):
    sources = list(LIVE_SERVERS if sources is None else sources)
    previous = previous or {}
    selected = {source["url"] for source in sources}
    entries = [{key: value for key, value in entry.items() if not key.startswith("_")}
               for entry in previous.get("entries", [])
               if entry_source(entry, LIVE_SERVERS) not in selected]
    source_status = [status for status in previous.get("sources", []) if status["url"] not in selected]
    verified_at = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {executor.submit(inventory_source, dict(source)): source for source in sources}
        for future in as_completed(future_map):
            source = future_map[future]
            source_entries, status = future.result()
            source_entries, status = merge_source_refresh(
                previous, source_entries, status, source, LIVE_SERVERS, verified_at)
            entries.extend(source_entries)
            source_status.append(status)
            print(f"[{status['status']}] {status['institution']} - {status['name']}: "
                  f"{status['entries']} entries ({status['retained_entries']} retained)", flush=True)
    entries = deduplicate(entries)
    return {
        "schema_version": CATALOG_SCHEMA_VERSION, "generated_at": verified_at,
        "entry_count": len(entries),
        "sources": sorted(source_status, key=lambda item: (item["institution"], item["name"])),
        "entries": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "catalog" / "catalog.json")
    parser.add_argument("--previous", type=Path, help="Previous inventory; defaults to output if it exists")
    parser.add_argument("--source", action="append", help="Exact institution name or source URL; repeatable")
    args = parser.parse_args()
    sources = list(LIVE_SERVERS)
    if args.source:
        sources = [source for source in sources if source["institution"] in args.source or source["url"] in args.source]
        matched = {value for source in sources for value in (source["institution"], source["url"])}
        unknown = set(args.source) - matched
        if unknown:
            parser.error(f"Unknown sources: {', '.join(sorted(unknown))}")
    previous_path = args.previous or args.output
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else {}
    catalog = build_catalog(sources, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + ".new")
    pending.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(args.output)
    print(f"Wrote {catalog['entry_count']} entries to {args.output}")


if __name__ == "__main__":
    main()
