"""Build the offline PeruSpatial Hub inventory from official REST/WMS roots."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from peruspatial_hub_catalog import CATALOG_SCHEMA_VERSION, normalize_search_text
from peruspatial_hub_sources import LIVE_SERVERS
from peruspatial_hub_urls import (
    append_rest_path,
    clean_rest_url,
    service_url,
    url_with_json,
    wms_capabilities_url,
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

    with ThreadPoolExecutor(max_workers=6) as executor:
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
        "status": "ok" if not errors else "partial",
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
    errors = []
    entries = [
        finalize_entry(
            {
                "type": "ogc_service",
                "stype": "wms",
                "url": source["url"],
                "service_url": clean_rest_url(source["url"]),
                "name": source["name"],
                "institution": source["institution"],
                "category": source["category"],
                "description": f"Servicio WMS inventariado de {source['institution']}.",
                "display_type": "Servicio WMS",
                "path": f"{source['institution']} / {source['name']}",
                "is_loaded": False,
            }
        )
    ]
    try:
        payload = read_url(
            wms_capabilities_url(source["url"]),
            "application/xml,text/xml",
            timeout=30,
        )
        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise RuntimeError("WMS document contains a disallowed DTD/entity")
        root = ET.fromstring(payload)
        capability = next((item for item in root.iter() if local_name(item.tag) == "Capability"), None)
        root_layer = direct_children(capability, "Layer")[0] if capability is not None else None
        if root_layer is None:
            raise RuntimeError("WMS did not publish a root Layer")

        service_url_value = clean_rest_url(source["url"])

        def walk(layer, inherited_crs, path):
            own_crs = [
                (child.text or "").strip()
                for child in list(layer)
                if local_name(child.tag) in {"CRS", "SRS"} and (child.text or "").strip()
            ]
            available_crs = list(dict.fromkeys(own_crs or inherited_crs))
            title = direct_text(layer, "Title") or "Capa WMS"
            layer_name = direct_text(layer, "Name")
            current_path = f"{path} / {title}"
            if layer_name:
                entries.append(
                    finalize_entry(
                        {
                            "type": "wms_layer",
                            "stype": "wms",
                            "url": source["url"],
                            "service_url": service_url_value,
                            "layer_name": layer_name,
                            "name": title,
                            "institution": source["institution"],
                            "category": source["category"],
                            "crs_options": available_crs,
                            "description": f"Capa WMS inventariada de {source['institution']}.",
                            "display_type": "Capa WMS",
                            "path": current_path,
                            "is_loaded": True,
                        }
                    )
                )
            for child_layer in direct_children(layer, "Layer"):
                walk(child_layer, available_crs, current_path)

        walk(root_layer, [], source["institution"])
    except Exception as exc:
        errors.append(str(exc))

    return entries, {
        "institution": source["institution"],
        "name": source["name"],
        "url": source["url"],
        "type": "wms",
        "entries": len(entries),
        "status": "ok" if not errors else "partial",
        "errors": errors,
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


def deduplicate(entries):
    unique = {}
    for entry in entries:
        key = (
            entry.get("type"),
            clean_rest_url(entry.get("url", "")),
            entry.get("layer_id"),
            entry.get("layer_name"),
        )
        unique[key] = entry
    return sorted(
        unique.values(),
        key=lambda item: (
            normalize_search_text(item.get("institution")),
            normalize_search_text(item.get("name")),
            str(item.get("url", "")),
        ),
    )


def build_catalog():
    entries = []
    source_status = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(inventory_source, dict(source)): source
            for source in LIVE_SERVERS
        }
        for future in as_completed(future_map):
            source_entries, status = future.result()
            entries.extend(source_entries)
            source_status.append(status)
            print(
                f"[{status['status']}] {status['institution']} - {status['name']}: "
                f"{status['entries']} entries",
                flush=True,
            )

    entries = deduplicate(entries)
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
        "sources": sorted(source_status, key=lambda item: (item["institution"], item["name"])),
        "entries": entries,
    }


if __name__ == "__main__":
    catalog = build_catalog()
    output = ROOT / "catalog" / "catalog.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {catalog['entry_count']} entries to {output}")
