"""Exercise the actual QGIS panel in an isolated profile, without a desktop session."""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--plugin-root", type=Path, default=ROOT)
    parser.add_argument("--institution", action="append", help="Limit live provider checks to named institutions")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt, QByteArray, QXmlStreamReader, QSize
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtWidgets import QMainWindow, QTreeWidgetItem
    from qgis.core import (QgsApplication, QgsProject, QgsSettings, QgsMapSettings, QgsDataSourceUri,
                           QgsMapRendererParallelJob, QgsCoordinateReferenceSystem, QgsRectangle)

    QCoreApplication.setOrganizationName("PeruSpatialHubAudit")
    QCoreApplication.setApplicationName("IsolatedSmoke")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(args.output / "settings"))
    app = QgsApplication([], False, str(args.output / "profile"))
    app.initQgis()
    # QgsApplication may reset Qt's settings path while initializing profiles.
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(args.output / "settings"))
    settings_path = Path(QgsSettings().fileName()).resolve()
    if args.output.resolve() not in settings_path.parents:
        raise RuntimeError(f"QGIS settings are not isolated: {settings_path}")
    QgsSettings().setValue("network/timeout", 12000)
    plugin_root = args.plugin_root.resolve()
    spec = importlib.util.spec_from_file_location("peru_audit_plugin", plugin_root / "__init__.py",
                                                 submodule_search_locations=[str(plugin_root)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    from peru_audit_plugin import peruspatial_hub_panel as ui
    from peru_audit_plugin.peruspatial_hub_sources import LIVE_SERVERS

    window = QMainWindow()
    messages = []
    iface = SimpleNamespace(mainWindow=lambda: window,
        messageBar=lambda: SimpleNamespace(pushMessage=lambda *a, **kw: messages.append(a)),
        reloadConnections=lambda: None,
        addPluginToMenu=lambda *a: None, removePluginMenu=lambda *a: None,
        addToolBarIcon=lambda *a: None, removeToolBarIcon=lambda *a: None,
        addDockWidget=lambda area, dock: window.addDockWidget(area, dock),
        removeDockWidget=lambda dock: window.removeDockWidget(dock))
    plugin = package.classFactory(iface)
    plugin.initGui()
    plugin.run()
    panel = plugin.dock_widget
    window.resize(1050, 950)
    window.show()
    app.processEvents()
    checks = []
    auth_uri = QgsDataSourceUri()
    auth_uri.setParam("url", "https://example.test/wms")
    auth_uri.setAuthConfigId("test000")
    assert "authcfg" in bytes(auth_uri.encodedUri()).decode("utf-8")
    checks.append({"check": "Generic URI auth configuration", "encoded_authcfg":
                   "authcfg" in bytes(auth_uri.encodedUri()).decode("utf-8")})

    reader = QXmlStreamReader(QByteArray(b"<root/>"))
    reader.readNextStartElement()
    checks.append({"check": "Qt XML name binding", "type": type(reader.name()).__name__,
                   "legacy_toString_available": hasattr(reader.name(), "toString")})
    assert len(panel.live_servers) == len(LIVE_SERVERS)
    checks.append({"check": "All configured sources visible", "count": len(panel.live_servers)})
    wms = b'''<WMS_Capabilities><Capability><Layer><Title>Root</Title><CRS>EPSG:4326</CRS>
    <Layer><Name>test</Name><Title>Test</Title><CRS>EPSG:3857</CRS></Layer>
    </Layer></Capability></WMS_Capabilities>'''
    node = QTreeWidgetItem(panel.tree_widget)
    data = {"url": "https://example.test/wms?map=peru", "institution": "Fixture", "category": "Clima y Riesgos"}
    panel.populate_wms_layers(node, data, wms)
    leaf = node.child(0).data(0, Qt.ItemDataRole.UserRole)
    assert leaf["crs_options"] == ["EPSG:4326", "EPSG:3857"]
    assert leaf["service_url"].endswith("?map=peru")
    checks.append({"check": "WMS importable layer, inherited CRS and vendor query", "passed": True})

    QgsSettings().setValue(panel.FAVORITES_SETTINGS_KEY, '[null, "bad", {"url":"https://example.test","name":"Valid"}]')
    assert len(panel.load_favorites()) == 1
    panel.populate_favorites_tree()
    checks.append({"check": "Malformed favorites handled", "passed": True})

    created_tasks = []

    class FakeTask:
        def __init__(self, done):
            self.done = done

        def cancel(self):
            pass

    def task_factory(name, worker, on_finished):
        task = FakeTask(on_finished)
        created_tasks.append(task)
        return task

    original_task, original_app = ui.QgsTask, ui.QgsApplication
    ui.QgsTask = SimpleNamespace(fromFunction=task_factory)
    ui.QgsApplication = SimpleNamespace(taskManager=lambda: SimpleNamespace(addTask=lambda task: None))
    try:
        node = QTreeWidgetItem(panel.tree_widget)
        node.setData(0, Qt.ItemDataRole.UserRole, {"url": "https://example.test/rest/services",
            "type": "server", "stype": "arcgis_rest", "name": "Fixture", "institution": "Fixture",
            "category": "Clima y Riesgos", "is_loaded": False})
        panel.load_dynamic_node(node)
        old = created_tasks[-1]
        panel.load_dynamic_node(node)
        new = created_tasks[-1]
        def directory(name):
            return "arcgis_directory", {"folders": [], "services": [{"name": name, "type": "MapServer"}]}
        new.done(None, directory("Current"))
        old.done(None, directory("Obsolete"))
        assert node.childCount() == 1 and node.child(0).text(0) == "Current"
        checks.append({"check": "Out-of-order refresh cannot overwrite latest result", "passed": True})
        panel.load_dynamic_node(node)
        detached_task = created_tasks[-1]
        panel.tree_widget.clear()
        detached_task.done(None, directory("Detached"))
        checks.append({"check": "Callback after removed tree item is safe", "passed": True})
    finally:
        ui.QgsTask, ui.QgsApplication = original_task, original_app

    panel.populate_tree()
    QgsSettings().remove(panel.FAVORITES_SETTINGS_KEY)
    panel.search_input.setText("geologia")
    panel.apply_catalog_search()
    assert panel.search_results_root.childCount() > 0
    checks.append({"check": "Local search in real QGIS tree", "results": panel.search_results_root.childCount()})
    panel.search_input.clear()
    panel.apply_catalog_search()

    if args.live:
        live_results = []
        raster_layers = []
        for institution, layer_type in [("MIDAGRI", "arcgis_map_layer"), ("SENAMHI", "wms_layer"),
                                        ("INGEMMET (GEOCATMIN)", "arcgis_raster_layer")]:
            if args.institution and institution not in args.institution:
                continue
            entry = next(entry for entry in panel.catalog_entries
                         if entry["institution"] == institution and entry["type"] == layer_type
                         and not entry.get("stale"))
            layer, errors = panel._instantiate_layer(entry)
            valid = layer is not None and layer.isValid()
            live_results.append({"institution": institution, "url": entry["url"], "valid": valid,
                                 "errors": errors, "provider": layer.providerType() if layer else None})
            if valid:
                QgsProject.instance().addMapLayer(layer)
                if layer_type in {"wms_layer", "arcgis_raster_layer"}:
                    raster_layers.append(layer)
            if institution == "MIDAGRI":
                raster = panel.create_arcgis_map_layer(entry["service_url"], entry["layer_id"], "MapServer raster")
                live_results.append({"institution": institution, "url": entry["service_url"],
                                     "valid": raster.isValid(), "provider": raster.providerType(),
                                     "errors": [] if raster.isValid() else [panel.provider_error(raster)]})
                if raster.isValid():
                    QgsProject.instance().addMapLayer(raster)
                    raster_layers.append(raster)
        if not args.institution or "INGEMMET (GEOCATMIN)" in args.institution:
            service = next(entry for entry in panel.catalog_entries if entry.get("type") == "arcgis_service"
                           and entry.get("service_kind") == "MapServer" and entry.get("name") == "SERV_GEOLOGIA_100K_INTEGRADA")
            leaf = next(entry for entry in panel.catalog_entries if entry.get("service_url") == service["url"]
                        and entry.get("type") == "arcgis_map_layer" and "geolog" in entry.get("name", "").casefold())
            for entry in (service, dict(leaf, prefer_raster=True)):
                raster, errors = panel._instantiate_layer(entry)
                valid = raster is not None and raster.isValid()
                live_results.append({"institution": entry["institution"], "url": entry["url"], "valid": valid,
                                     "errors": errors, "provider": raster.providerType() if raster else None})
                if valid:
                    assert raster.providerType() == "arcgismapserver"
                    raster.setCustomProperty("peruspatial_qa_detail_extent", True)
                    QgsProject.instance().addMapLayer(raster)
                    raster_layers.append(raster)
        checks.append({"check": "Live native providers", "results": live_results})
        (args.output / "qgis-smoke.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        assert all(result["valid"] for result in live_results), live_results
        render_results = []
        checks.append({"check": "Live raster rendering over Peru", "results": render_results})
        for index, layer in enumerate(raster_layers):
            settings = QgsMapSettings()
            settings.setLayers([layer])
            settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
            settings.setExtent(QgsRectangle(-82, -19, -68, 0))
            if layer.customProperty("peruspatial_qa_detail_extent", False):
                settings.setExtent(QgsRectangle(-75.2, -12.2, -75.0, -12.0))
            settings.setOutputSize(QSize(640, 480))
            settings.setBackgroundColor(QColor("white"))
            job = QgsMapRendererParallelJob(settings)
            job.start()
            deadline = time.monotonic() + 30
            while job.isActive() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.02)
            if job.isActive():
                job.cancel()
                render_results.append({"layer": layer.name(), "colors": 0,
                    "errors": ["Rendering exceeded the 30 second test deadline"], "timeout": True})
                (args.output / "qgis-smoke.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
                continue
            image = job.renderedImage()
            colors = {image.pixel(x, y) for x in range(0, image.width(), 7)
                      for y in range(0, image.height(), 7)}
            errors = [error.message for error in job.errors()]
            image.save(str(args.output / f"native-render-{index}.png"))
            render_results.append({"layer": layer.name(), "colors": len(colors), "errors": errors})
            (args.output / "qgis-smoke.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        (args.output / "qgis-smoke.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        assert all(result["colors"] > 1 and not result["errors"] for result in render_results), render_results

    app.processEvents()
    window.grab().save(str(args.output / "panel.png"))
    panel.cancel_background_tasks()
    assert panel._shutting_down
    checks.append({"check": "Unload cancels pending work", "passed": True})
    assert plugin.dock_widget is not None and plugin.action is not None
    plugin.unload()
    assert plugin.dock_widget is None and plugin.action is None
    app.processEvents()
    checks.append({"check": "Packaged plugin controller init, run and unload", "passed": True})
    (args.output / "qgis-smoke.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2), flush=True)
    QgsProject.instance().removeAllMapLayers()
    window.close()
    window.deleteLater()
    app.processEvents()
    # QGIS owns providers and QObject lifetimes until process exit.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
