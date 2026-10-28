"""Validate inventoried CRS definitions and representative schemas using QGIS."""

import argparse
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "catalog/catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QGIS_AUTH_DB_DIR_PATH"] = str(args.output / "auth")
    (args.output / "auth").mkdir(exist_ok=True)
    from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsSettings, Qgis
    from qgis.PyQt.QtCore import QSettings
    from qgis.PyQt.QtWidgets import QMainWindow

    app = QgsApplication([], True, str(args.output / "profile"))
    app.initQgis()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(args.output / "settings"))
    assert args.output.resolve() in Path(QgsSettings().fileName()).resolve().parents
    QgsSettings().setValue("network/timeout", 12000)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    references = defaultdict(list)
    wms_codes = set()
    for entry in catalog["entries"]:
        if entry.get("spatial_reference"):
            references[json.dumps(entry["spatial_reference"], sort_keys=True)].append(entry)
        wms_codes.update(entry.get("crs_options", []))
    report = {"qgis": Qgis.QGIS_VERSION, "catalog_entries": len(catalog["entries"]),
              "rest_crs": [], "wms_crs": [], "unmarked_psad56": [], "native_schema_checks": []}
    for definition, entries in references.items():
        sr = json.loads(definition)
        wkid = sr.get("latestWkid") or sr.get("wkid")
        crs = QgsCoordinateReferenceSystem()
        if isinstance(wkid, int) and wkid > 0:
            crs = QgsCoordinateReferenceSystem.fromEpsgId(wkid)
            if not crs.isValid():
                crs = QgsCoordinateReferenceSystem(f"ESRI:{wkid}")
        if not crs.isValid() and sr.get("wkt"):
            crs = QgsCoordinateReferenceSystem.fromWkt(sr["wkt"])
        item = {"wkid": wkid, "valid": crs.isValid(), "authid": crs.authid(),
                "name": crs.description(), "entries": len(entries),
                "sample_url": entries[0]["url"], "has_wkt": bool(sr.get("wkt"))}
        report["rest_crs"].append(item)
        if crs.isValid() and crs.geographicCrsAuthId() == "EPSG:4248":
            report["unmarked_psad56"].extend({"url": entry["url"], "wkid": wkid, "name": entry["name"]}
                                            for entry in entries if not entry.get("crs_warning"))
    for code in sorted(wms_codes):
        crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(code)
        report["wms_crs"].append({"code": code, "valid": crs.isValid(), "authid": crs.authid()})
    supported_codes = {item["code"] for item in report["wms_crs"] if item["valid"]}
    report["wms_layers_without_supported_crs"] = [entry["url"] + "#" + entry["layer_name"]
        for entry in catalog["entries"] if entry.get("type") == "wms_layer"
        and not supported_codes.intersection(entry.get("crs_options", []))]
    if args.live:
        spec = importlib.util.spec_from_file_location("peru_inventory_qgis", ROOT / "__init__.py",
            submodule_search_locations=[str(ROOT)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = package
        spec.loader.exec_module(package)
        from peru_inventory_qgis.peruspatial_hub_panel import PeruSpatialHubPanel
        window = QMainWindow()
        iface = SimpleNamespace(mainWindow=lambda: window, reloadConnections=lambda: None)
        panel = PeruSpatialHubPanel(iface, window, str(ROOT))
        public = [entry for entry in catalog["entries"] if not entry.get("stale")]
        samples = [next(entry for entry in public if entry.get("is_table") and entry.get("field_count")),
                   next(entry for entry in public if "duplicate_field_names" in entry.get("metadata_warnings", [])
                        and entry.get("institution") == "MINCUL")]
        samples.extend(entry for entry in public if entry.get("inventory_discovery") == "bulk_verified")
        for entry in samples:
            layer, errors = panel._instantiate_layer(entry)
            valid = layer is not None and layer.isValid()
            report["native_schema_checks"].append({"url": entry["url"], "name": entry["name"],
                "is_table": entry.get("is_table"), "valid": valid, "errors": errors,
                "provider": layer.providerType() if layer else None,
                "declared_fields": entry.get("field_count"),
                "native_fields": len(layer.fields()) if valid and hasattr(layer, "fields") else None,
                "native_spatial": layer.isSpatial() if valid and hasattr(layer, "isSpatial") else None})
        panel.cancel_background_tasks()
        window.close()
    (args.output / "qgis-inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"qgis": report["qgis"], "rest_crs_definitions": len(report["rest_crs"]),
        "unresolved_rest_crs": sum(not item["valid"] for item in report["rest_crs"]),
        "wms_crs_definitions": len(report["wms_crs"]), "unresolved_wms_crs": sum(not item["valid"] for item in report["wms_crs"]),
        "unmarked_psad56": len(report["unmarked_psad56"]),
        "wms_layers_without_supported_crs": len(report["wms_layers_without_supported_crs"]),
        "native_schema_checks": report["native_schema_checks"]}, indent=2), flush=True)
    assert all(item["valid"] for item in report["rest_crs"]), "Published REST CRS definitions must resolve in QGIS"
    assert not report["unmarked_psad56"], "Declared PSAD56 must carry the datum reminder"
    assert not report["wms_layers_without_supported_crs"], "Each WMS layer needs an advertised CRS supported by QGIS"
    assert all(item["valid"] for item in report["native_schema_checks"])
    assert all(not item["native_spatial"] for item in report["native_schema_checks"] if item["is_table"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
