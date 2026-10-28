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
    return normalize_search_text(
        " ".join(
            str(entry.get(field, ""))
            for field in ("name", "institution", "category", "path", "display_type")
        )
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
        ranked.append((score, name, position, entry))

    ranked.sort(key=lambda item: item[:3])
    total = len(ranked)
    return [item[3] for item in ranked[: max(1, int(limit))]], total
