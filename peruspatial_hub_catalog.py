"""Load and search the bundled service inventory without network access."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path


CATALOG_SCHEMA_VERSION = 1


def is_psad56_reference(spatial_reference):
    """Recognize an explicitly declared PSAD56 datum without changing coordinates."""
    if not isinstance(spatial_reference, dict):
        return False
    wkid = spatial_reference.get("latestWkid") or spatial_reference.get("wkid")
    wkt = str(spatial_reference.get("wkt") or spatial_reference.get("wkt2") or "").casefold()
    return str(wkid) == "4248" or "psad" in wkt or "provisional_south_american_datum_1956" in wkt


def arcgis_data_kind(record):
    """Describe the published resource separately from its QGIS loading route."""
    kind = str(record.get("type", "")).casefold().replace(" ", "")
    if record.get("is_table") or kind == "table":
        return "tabla"
    if kind in {"grouplayer", "subtypegrouplayer"} or record.get("subLayerIds") or record.get("subLayers"):
        return "grupo"
    if record.get("geometryType") or kind == "featurelayer":
        return "vectorial"
    if "raster" in kind or "mosaic" in kind:
        return "raster"
    return "mixto"


def arcgis_metadata_fields(record, service_metadata, is_table=False, is_image=False):
    """Shared compact metadata for live tree nodes and the bundled inventory."""
    data_kind = "raster" if is_image else arcgis_data_kind(dict(record, is_table=is_table or record.get("is_table", False)))
    is_table = data_kind == "tabla"
    result = {"data_kind": data_kind, "is_table": is_table}
    if record.get("geometryType") and not is_table:
        result["geometry_type"] = record["geometryType"]
    warnings = list(record.get("metadata_warnings") or [])
    if isinstance(record.get("fields"), list):
        result["field_count"] = len(record["fields"])
        names = [field.get("name") for field in record["fields"] if isinstance(field, dict)]
        if len(names) != len(set(names)):
            warnings.append("duplicate_field_names")
    if warnings:
        result["metadata_warnings"] = sorted(set(warnings))
    if isinstance(record.get("capabilities"), str):
        result["capabilities"] = record["capabilities"]
    extent = record.get("extent") or service_metadata.get("fullExtent") or {}
    extent = extent if isinstance(extent, dict) else {}
    if extent and not is_table:
        result["extent"] = extent
    reference = record.get("spatialReference") or extent.get("spatialReference") or service_metadata.get("spatialReference")
    if isinstance(reference, dict) and reference and not is_table:
        result["spatial_reference"] = reference
        if is_psad56_reference(reference):
            result["crs_warning"] = True
    for key, target in (("minScale", "min_scale"), ("maxScale", "max_scale")):
        if isinstance(record.get(key), (int, float)):
            result[target] = record[key]
    return result


def arcgis_directory(metadata):
    """Validate directory content before treating it as a complete inventory."""
    if not isinstance(metadata, dict) or not any(key in metadata for key in ("folders", "services")):
        raise ValueError("la respuesta no es un directorio ArcGIS REST")
    folders, services = metadata.get("folders", []), metadata.get("services", [])
    if not isinstance(folders, list) or not isinstance(services, list):
        raise ValueError("el directorio ArcGIS no contiene listas válidas de carpetas y servicios")
    if any(not isinstance(folder, str) or not folder.strip() for folder in folders):
        raise ValueError("el directorio ArcGIS contiene una carpeta inválida")
    if any(not isinstance(service, dict) or not isinstance(service.get("name"), str)
           or not service["name"].strip() or not isinstance(service.get("type"), str) for service in services):
        raise ValueError("el directorio ArcGIS contiene un servicio inválido")
    return folders, services


def arcgis_service_records(metadata, service_kind):
    """Validate layer identities and hierarchy before inventory/tree construction."""
    if not isinstance(metadata, dict):
        raise ValueError("los metadatos del servicio ArcGIS no son un objeto")
    if service_kind == "ImageServer":
        if not any(key in metadata for key in ("pixelType", "bandCount", "serviceDataType")):
            raise ValueError("la respuesta no contiene metadatos de ImageServer")
        return []
    if not any(key in metadata for key in ("layers", "tables")):
        raise ValueError("el servicio ArcGIS no contiene un inventario de capas o tablas")
    records = []
    seen = set()
    for is_table, key in ((False, "layers"), (True, "tables")):
        values = metadata.get(key, [])
        if not isinstance(values, list):
            raise ValueError("el inventario ArcGIS de capas o tablas no es una lista")
        for value in values:
            if not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] < 0:
                raise ValueError("el inventario ArcGIS contiene un ID de capa inválido")
            if value["id"] in seen:
                raise ValueError("el inventario ArcGIS contiene IDs de capa duplicados")
            seen.add(value["id"])
            record = dict(value, is_table=is_table or str(value.get("type", "")).casefold() == "table")
            if "parentLayerId" not in record and isinstance(record.get("parentLayer"), dict):
                record["parentLayerId"] = record["parentLayer"].get("id", -1)
            records.append(record)
    by_id = {record["id"]: record for record in records}
    checked = set()
    for record in records:
        chain = set()
        current = record["id"]
        while current in by_id and current not in checked:
            if current in chain:
                raise ValueError("el inventario ArcGIS contiene un ciclo entre grupos de capas")
            chain.add(current)
            current = by_id[current].get("parentLayerId", -1)
        checked.update(chain)
    return records


def resolve_arcgis_inventory(metadata, service_kind, fetch_part, cancelled=None, max_requests=256):
    """Reconcile summaries, bulk metadata and explicitly referenced sublayers.

    fetch_part receives an integer layer ID or 'layers'. Unlisted IDs are
    accepted only after their individual endpoint confirms the same ID.
    """
    listed = arcgis_service_records(metadata, service_kind)
    if service_kind == "ImageServer":
        return dict(metadata, _inventory_complete=True, _inventory_errors=[])
    records = {record["id"]: dict(record) for record in listed}
    detailed_ids, errors, unlisted = set(), [], []
    try:
        if cancelled and cancelled():
            raise RuntimeError("carga cancelada")
        bulk = arcgis_service_records(fetch_part("layers"), service_kind)
        for record in bulk:
            if record["id"] in records:
                records[record["id"]].update(record)
                detailed_ids.add(record["id"])
            else:
                unlisted.append(record)
    except Exception:
        bulk = []
    if cancelled and cancelled():
        raise RuntimeError("carga cancelada")
    requests = 0

    def fetch_id(layer_id, parent_id=None, template=None):
        nonlocal requests
        if cancelled and cancelled():
            raise RuntimeError("carga cancelada")
        requests += 1
        if requests > max_requests:
            raise ValueError("se alcanzó el límite de consultas adicionales de subcapas")
        detail = fetch_part(layer_id)
        if not isinstance(detail, dict) or detail.get("id") != layer_id:
            raise ValueError("los metadatos no corresponden al ID solicitado")
        record = dict(template or {}, **detail)
        if parent_id is not None and "parentLayerId" not in record and not record.get("parentLayer"):
            record["parentLayerId"] = parent_id
        normalized = arcgis_service_records({"tables" if record.get("is_table") else "layers": [record]}, service_kind)[0]
        records[layer_id] = normalized
        detailed_ids.add(layer_id)

    for record in unlisted:
        try:
            fetch_id(record["id"], template=record)
            records[record["id"]]["inventory_discovery"] = "bulk_verified"
        except Exception as exc:
            errors.append(f"ID {record['id']} anunciado solo en metadatos completos: {exc}")
    visited, failed_ids, pending = set(), set(), list(records)
    while pending:
        if cancelled and cancelled():
            raise RuntimeError("carga cancelada")
        layer_id = pending.pop()
        if layer_id in visited:
            continue
        visited.add(layer_id)
        record = records[layer_id]
        children = list(record.get("subLayerIds") or [])
        children.extend(child.get("id") for child in (record.get("subLayers") or []) if isinstance(child, dict))
        for child in dict.fromkeys(children):
            if type(child) is not int or child < 0:
                errors.append(f"Grupo {layer_id}: referencia de subcapa inválida ({child})")
                record.setdefault("metadata_warnings", []).append("missing_sublayers")
            elif child not in records:
                try:
                    if child in failed_ids:
                        raise ValueError("la subcapa ya respondió con error")
                    fetch_id(child, parent_id=layer_id)
                    records[child]["inventory_discovery"] = "reference_verified"
                    pending.append(child)
                except Exception as exc:
                    failed_ids.add(child)
                    errors.append(f"Grupo {layer_id}, subcapa {child}: {exc}")
                    record.setdefault("metadata_warnings", []).append("missing_sublayers")
    result = dict(metadata,
        layers=[record for record in records.values() if not record.get("is_table")],
        tables=[record for record in records.values() if record.get("is_table")],
        _inventory_complete=not errors, _inventory_errors=sorted(set(errors)),
        _inventory_detailed_ids=sorted(detailed_ids))
    arcgis_service_records(result, service_kind)
    return result


def normalize_search_text(value: object) -> str:
    """Normalize case, accents and whitespace for predictable local search."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(plain.casefold().split())


def entry_search_text(entry: dict) -> str:
    """Return the precomputed haystack or derive one for older inventories."""
    precomputed = normalize_search_text(entry.get("search_text"))
    if precomputed:
        return precomputed
    formats = (" mapa raster MapServer" if entry.get("type") == "arcgis_service" and entry.get("service_kind") == "MapServer"
               else " raster" if entry.get("type") in {"wms_layer", "arcgis_raster_layer"} else "")
    return normalize_search_text(
        " ".join(
            str(entry.get(field, ""))
            for field in ("name", "institution", "category", "path", "display_type")
        ) + formats
    )


def load_catalog(path) -> dict:
    """Load and validate a bundled catalog, returning an empty fallback on absence."""
    catalog_path = Path(path)
    if not catalog_path.is_file():
        return {"schema_version": CATALOG_SCHEMA_VERSION, "entries": [], "sources": []}

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("el inventario no es un objeto JSON")
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ValueError("versión de inventario no compatible")
    if not isinstance(payload.get("entries"), list):
        raise ValueError("el inventario no contiene una lista de entradas")
    sources = payload.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(source, dict) for source in sources):
        raise ValueError("el inventario no contiene una lista válida de fuentes")
    if "entry_count" in payload and payload["entry_count"] != len(payload["entries"]):
        raise ValueError("el recuento del inventario no coincide con sus entradas")
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) and entry[key]
                                                  for key in ("name", "url", "type")):
            raise ValueError("el inventario contiene una entrada inválida")
        entry["_search_text"] = entry_search_text(entry)
    return payload


def search_catalog(entries, query: object, category: str, limit: int = 200):
    """Search the inventory locally and return ranked results plus total matches."""
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return [], 0

    tokens = normalized_query.split()
    ranked = []
    for position, entry in enumerate(entries):
        if category and category != "Todas las Categorías":
            if entry.get("category") != category:
                continue

        haystack = entry.get("_search_text") or entry_search_text(entry)
        if not all(token in haystack for token in tokens):
            continue

        name = normalize_search_text(entry.get("name"))
        if name == normalized_query:
            score = 0
        elif name.startswith(normalized_query):
            score = 1
        elif normalized_query in name:
            score = 2
        else:
            score = 3
        # Keep the complete rendered map visible before its many sublayers.
        map_priority = 0 if entry.get("type") == "arcgis_service" and entry.get("service_kind") == "MapServer" else 1
        ranked.append((score, map_priority, name, position, entry))

    ranked.sort(key=lambda item: item[:4])
    total = len(ranked)
    return [item[4] for item in ranked[: max(1, int(limit))]], total
