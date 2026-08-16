import ast
import json
from pathlib import Path

from peruspatial_hub_catalog import load_catalog, normalize_search_text, search_catalog


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "catalog.json"


def test_normalization_ignores_accents_case_and_repeated_spaces():
    assert normalize_search_text("  GEOLOGÍA   Histórica ") == "geologia historica"


def test_search_ranks_names_filters_categories_and_limits_results():
    entries = [
        {
            "name": "Geología Nacional",
            "institution": "IGN",
            "category": "Geología y Minería",
            "path": "Mapas",
        },
        {
            "name": "Mapa Nacional",
            "institution": "MINAM",
            "category": "Medio Ambiente",
            "path": "Temas / Geología",
        },
        {
            "name": "Geología Regional",
            "institution": "INGEMMET",
            "category": "Geología y Minería",
            "path": "Mapas",
        },
    ]
    for entry in entries:
        entry["_search_text"] = " ".join(
            normalize_search_text(entry[field])
            for field in ("name", "institution", "category", "path")
        )

    results, total = search_catalog(entries, "geologia", "Geología y Minería", limit=1)
    assert total == 2
    assert len(results) == 1
    assert results[0]["name"].startswith("Geología")


def test_bundled_catalog_is_large_valid_and_compact():
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["entry_count"] == len(raw["entries"])
    assert raw["entry_count"] >= 5000
    assert len(raw["sources"]) == 14
    assert all("search_text" not in entry for entry in raw["entries"])

    loaded = load_catalog(CATALOG_PATH)
    assert all(entry.get("_search_text") for entry in loaded["entries"])
    results, total = search_catalog(loaded["entries"], "geologia", "", limit=200)
    assert total >= len(results) > 0
    assert len(results) <= 200


def test_search_signal_path_contains_no_network_calls():
    source = (ROOT / "peruspatial_hub_panel.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    search_methods = {
        "schedule_filter_services",
        "apply_catalog_search",
        "populate_catalog_results",
    }
    forbidden = {
        "blockingGet",
        "fetch_arcgis_json",
        "load_dynamic_node",
        "read_service_https",
        "urlopen",
    }

    for method_name in search_methods:
        names = {
            node.id
            for node in ast.walk(methods[method_name])
            if isinstance(node, ast.Name)
        }
        attributes = {
            node.attr
            for node in ast.walk(methods[method_name])
            if isinstance(node, ast.Attribute)
        }
        assert forbidden.isdisjoint(names | attributes)

    assert "self.search_timer.timeout.connect(self.apply_catalog_search)" in source
    assert "perform_deep_search" not in source
