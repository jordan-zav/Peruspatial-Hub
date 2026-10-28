"""Run plugin lifecycle and native Browser checks inside a separate QGIS desktop."""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path(os.environ["PERUSPATIAL_DESKTOP_PLUGIN"])


def desktop_checks():
    from qgis import utils
    from qgis.core import QgsApplication, QgsProject, QgsSettings, QgsVectorLayer, Qgis
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import QTimer, Qt, QCoreApplication, QEvent
    from qgis.PyQt.QtGui import QFont, QFontDatabase
    from qgis.PyQt.QtTest import QTest
    from qgis.PyQt.QtWidgets import QTreeWidgetItem
    from qgis.gui import QgsBrowserTreeView

    output = Path(os.environ["PERUSPATIAL_DESKTOP_OUTPUT"])
    plugin_root = Path(os.environ["PERUSPATIAL_DESKTOP_PLUGIN"])
    iface = utils.iface
    results, errors = [], []
    plugin = None
    managed = os.environ.get("PERUSPATIAL_DESKTOP_INSTALL") == "1"
    hook = sys.excepthook
    sys.excepthook = lambda kind, value, tb: errors.append("".join(traceback.format_exception(kind, value, tb)))

    def record(name, detail):
        results.append({"check": name, "passed": True, "detail": detail})
        (output / "desktop-results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        settings_path = Path(QgsSettings().fileName()).resolve()
        assert output.resolve() in settings_path.parents, str(settings_path)
        record("isolated_desktop_profile", {"qgis": Qgis.QGIS_VERSION, "settings": str(settings_path)})
        if os.environ.get("PERUSPATIAL_DESKTOP_MODE") == "baseline":
            record("baseline_without_plugin", "No plugin imported or registered")
            return
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
        QgsApplication.instance().setFont(QFont("Segoe UI", 10))
        iface.mainWindow().resize(1440, 1000)
        if managed:
            utils.updateAvailablePlugins()
            assert "peruspatial_hub" in utils.available_plugins
            assert utils.loadPlugin("peruspatial_hub")
            assert utils.startPlugin("peruspatial_hub")
            plugin = utils.plugins["peruspatial_hub"]
            record("installed_plugin_manager_load", "Plugin discovered and started by the real QGIS plugin manager")
        else:
            spec = importlib.util.spec_from_file_location("peru_desktop_checks", plugin_root / "__init__.py",
                submodule_search_locations=[str(plugin_root)])
            package = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = package
            spec.loader.exec_module(package)
            plugin = package.classFactory(iface)
            plugin.initGui()
        plugin.action.trigger()
        panel = plugin.dock_widget
        assert panel and panel.isVisible()
        original_panel = panel
        plugin.action.trigger()
        assert plugin.dock_widget is original_panel
        record("toolbar_opens_single_dock", "Plugin action opens the real main-window dock without duplicates")
        QTest.keyClicks(panel.search_input, "geologia ingemmet")
        QTest.qWait(350)
        count = panel.search_results_root.childCount()
        assert 0 < count <= 200, count
        iface.mainWindow().grab().save(str(output / "desktop-search.png"))
        record("desktop_catalog_search", {"matches": count})
        panel.search_input.clear()
        QTest.qWait(250)
        panel.write_connection("Desktop QA WMS", "https://example.test/wms?map=peru", "wms")
        panel.write_connection("Desktop QA ArcGIS", "https://example.test/rest/services", "arcgis_rest")
        model = iface.browserModel()
        native = {}
        views = [view for view in iface.mainWindow().findChildren(QgsBrowserTreeView) if view.isVisible()]
        for row in range(model.rowCount()) if os.environ.get("PERUSPATIAL_DESKTOP_MODE") != "no-browser" else []:
            index = model.index(row, 0)
            label = str(model.data(index))
            if "wms" in label.casefold() or "arcgis" in label.casefold():
                assert views, "Native Browser view is not visible"
                for view in views:
                    proxy = view.model()
                    if hasattr(proxy, "mapFromSource") and proxy.sourceModel() is model:
                        view.expand(proxy.mapFromSource(index))
                if model.canFetchMore(index):
                    model.fetchMore(index)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    QgsApplication.processEvents()
                    names = [str(model.data(model.index(child, 0, index))) for child in range(model.rowCount(index))]
                    if any(name.startswith("Desktop QA") for name in names):
                        break
                    QTest.qWait(30)
                native[label] = names
        if os.environ.get("PERUSPATIAL_DESKTOP_MODE") != "no-browser":
            assert any("Desktop QA WMS" in names for names in native.values()), native
            assert any("Desktop QA ArcGIS" in names for names in native.values()), native
            record("native_browser_connections", native)

        # Exercise the Add button against the real project's layer tree and canvas.
        panel.tree_widget.clear()
        node = QTreeWidgetItem(panel.tree_widget)
        node.setText(0, "Desktop fixture")
        node.setData(0, Qt.ItemDataRole.UserRole, {"type": "arcgis_vector_layer", "stype": "arcgisfeatureserver",
            "name": "Desktop fixture", "url": "https://example.test/rest/services/Test/FeatureServer/0"})
        panel.tree_widget.setCurrentItem(node)
        panel._instantiate_layer = lambda data: (QgsVectorLayer("Point?crs=EPSG:4326", data["name"], "memory"), [])
        QTest.mouseClick(panel.btn_add_layer, Qt.MouseButton.LeftButton)
        assert len(QgsProject.instance().mapLayers()) == 1
        assert iface.layerTreeView().layerTreeModel().rootGroup().findLayers()
        record("desktop_add_layer_button", "Layer appears in the real QGIS project and Layers panel")
        panel.close()
        QgsApplication.processEvents()
        assert not panel.isVisible()
        plugin.action.trigger()
        assert plugin.dock_widget is original_panel and panel.isVisible()
        record("desktop_close_and_reopen", "Closing and reopening preserves the dock instance")
        iface.mainWindow().grab().save(str(output / "desktop-loaded.png"))
        if managed:
            assert utils.unloadPlugin("peruspatial_hub")
        else:
            plugin.unload()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert sip.isdeleted(panel)
        assert plugin.dock_widget is None and plugin.action is None
        record("desktop_unload", "Plugin dock and action are removed from the real interface")
        if managed:
            assert utils.loadPlugin("peruspatial_hub") and utils.startPlugin("peruspatial_hub")
            plugin = utils.plugins["peruspatial_hub"]
        else:
            plugin.initGui()
        plugin.action.trigger()
        assert plugin.dock_widget is not None and plugin.dock_widget.isVisible()
        if managed:
            assert utils.unloadPlugin("peruspatial_hub")
        else:
            plugin.unload()
        record("desktop_reload", "A fresh controller UI works after unload")
        assert not errors, errors
        record("qt_slot_exceptions", {"count": len(errors)})
    except Exception:
        results.append({"check": "desktop_failure", "passed": False, "error": traceback.format_exc(), "qt_errors": errors})
    finally:
        (output / "desktop-results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        iface.mainWindow().grab().save(str(output / "desktop-final.png"))
        if plugin and (plugin.dock_widget or plugin.action):
            if managed:
                utils.unloadPlugin("peruspatial_hub")
            else:
                plugin.unload()
        QgsProject.instance().removeAllMapLayers()
        QgsProject.instance().setDirty(False)
        sys.excepthook = hook
        # Exercise QGIS' normal close path, including native Browser state saving.
        QTimer.singleShot(100, iface.actionExit().trigger)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, default=ROOT)
    parser.add_argument("--qgis-bin", type=Path, required=True)
    parser.add_argument("--mode", choices=["full", "baseline", "no-browser"], default="full")
    parser.add_argument("--install", action="store_true", help="Install a package copy into the isolated profile and use QGIS' plugin manager")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plugin_root = args.plugin_root.resolve()
    if args.install:
        installed = args.output.resolve() / "profiles" / "profiles" / "PeruSpatialUIQA" / "python" / "plugins" / "peruspatial_hub"
        shutil.copytree(plugin_root, installed)
        plugin_root = installed
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM="offscreen", PERUSPATIAL_DESKTOP_OUTPUT=str(args.output.resolve()),
        PERUSPATIAL_DESKTOP_PLUGIN=str(plugin_root), PERUSPATIAL_DESKTOP_INSTALL="1" if args.install else "0",
        PERUSPATIAL_DESKTOP_MODE=args.mode,
        QGIS_AUTH_DB_DIR_PATH=str(args.output.resolve() / "auth"))
    (args.output / "auth").mkdir(exist_ok=True)
    command = [str(args.qgis_bin), "--profiles-path", str(args.output.resolve() / "profiles"),
        "--profile", "PeruSpatialUIQA", "--nologo", "--noplugins", "--noversioncheck", "--nocustomization",
        "--code", str(Path(__file__).resolve())]
    started = time.monotonic()
    with (args.output / "qgis-console.log").open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=False)
        except subprocess.TimeoutExpired:
            (args.output / "process-result.json").write_text(json.dumps({"passed": False, "timeout": True}), encoding="utf-8")
            raise
    (args.output / "process-result.json").write_text(json.dumps({"passed": result.returncode == 0,
        "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 2), "mode": args.mode}), encoding="utf-8")
    report = args.output / "desktop-results.json"
    if not report.is_file():
        raise RuntimeError(f"QGIS did not produce a result report (exit {result.returncode}); see {log.name}")
    results = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 1 if result.returncode != 0 or any(not entry["passed"] for entry in results) else 0


if os.environ.get("PERUSPATIAL_DESKTOP_OUTPUT"):
    from qgis.PyQt.QtCore import QTimer
    Path(os.environ["PERUSPATIAL_DESKTOP_OUTPUT"], "startup-entered.txt").write_text("QGIS startup script reached", encoding="utf-8")
    # --code runs during startup; wait until the actual main window is ready.
    QTimer.singleShot(1000, desktop_checks)
elif __name__ == "__main__":
    raise SystemExit(main())
