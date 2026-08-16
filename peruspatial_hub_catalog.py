"""Load and search the bundled service inventory without network access."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path


CATALOG_SCHEMA_VERSION = 1


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
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ValueError("versión de inventario no compatible")
    if not isinstance(payload.get("entries"), list):
        raise ValueError("el inventario no contiene una lista de entradas")
    for entry in payload["entries"]:
        if isinstance(entry, dict):
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
