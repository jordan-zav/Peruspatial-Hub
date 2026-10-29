"""Exercise panel widgets and event-loop edge cases with real QGIS/Qt objects."""

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, default=ROOT)
    parser.add_argument("--case", action="append")
    parser.add_argument("--live", action="store_true", help="Also verify all configured sources through a real QGIS task")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QGIS_AUTH_DB_DIR_PATH"] = str(args.output / "auth")
    (args.output / "auth").mkdir(exist_ok=True)

    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import Qt, QCoreApplication, QSettings, QTimer, QEvent
    from qgis.PyQt.QtGui import QFont, QPalette, QColor, QFontDatabase
    from qgis.PyQt.QtTest import QTest
    from qgis.PyQt.QtWidgets import QApplication, QMainWindow, QTreeWidgetItem, QMessageBox
    from qgis.core import QgsApplication, QgsProject, QgsSettings, QgsVectorLayer, QgsOwsConnection

    QCoreApplication.setOrganizationName("PeruSpatialHubUIAudit")
    QCoreApplication.setApplicationName("WidgetChecks")
    app = QgsApplication([], True, str(args.output / "profile"))
    app.initQgis()
    system_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if system_font.is_file():
        QFontDatabase.addApplicationFont(str(system_font))
    app.setFont(QFont("Segoe UI", 10))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(args.output / "settings"))
    if args.output.resolve() not in Path(QgsSettings().fileName()).resolve().parents:
        raise RuntimeError("Test QGIS settings are not isolated")

    spec = importlib.util.spec_from_file_location("peru_ui_checks", args.plugin_root / "__init__.py",
        submodule_search_locations=[str(args.plugin_root)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    from peru_ui_checks import peruspatial_hub_panel as ui

    results = []
    qt_errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda kind, value, tb: qt_errors.append("".join(traceback.format_exception(kind, value, tb)))

    def run_case(name, callback):
        if args.case and name not in args.case:
            return
        QgsSettings().setValue(ui.PeruSpatialHubPanel.FAVORITES_SETTINGS_KEY, "[]")
        QgsSettings().setValue(ui.PeruSpatialHubPanel.AUTH_SCOPES_SETTINGS_KEY, "{}")
        window = QMainWindow()
        messages, dialogs = [], []
        iface = SimpleNamespace(mainWindow=lambda: window,
            messageBar=lambda: SimpleNamespace(pushMessage=lambda *a, **kw: messages.append((a, kw))),
            reloadConnections=lambda: None)
        panel = ui.PeruSpatialHubPanel(iface, window, str(args.plugin_root))
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, panel)
        window.resize(650, 900)
        window.show()
        QTest.qWait(200)
        panel.search_timer.stop()
        error_index = len(qt_errors)
        original_warning, original_info, original_question = QMessageBox.warning, QMessageBox.information, QMessageBox.question
        QMessageBox.warning = lambda *a, **kw: dialogs.append(("warning", a[1:])) or QMessageBox.StandardButton.Ok
        QMessageBox.information = lambda *a, **kw: dialogs.append(("information", a[1:])) or QMessageBox.StandardButton.Ok
        QMessageBox.question = lambda *a, **kw: QMessageBox.StandardButton.No
        context = SimpleNamespace(panel=panel, window=window, messages=messages, dialogs=dialogs)
        started = time.monotonic()
        original_palette = QPalette(app.palette())
        original_style = app.style().objectName()
        try:
            detail = callback(context)
            app.processEvents()
            if len(qt_errors) > error_index:
                raise AssertionError(qt_errors[error_index:])
            result = {"case": name, "passed": True, "detail": detail}
        except Exception:
            result = {"case": name, "passed": False, "error": traceback.format_exc()}
        finally:
            if not sip.isdeleted(panel):
                panel.search_timer.stop()
                panel.cancel_background_tasks()
            if not sip.isdeleted(window):
                window.grab().save(str(args.output / (name + ".png")))
                window.close()
                window.deleteLater()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QMessageBox.warning, QMessageBox.information, QMessageBox.question = original_warning, original_info, original_question
            QgsProject.instance().removeAllMapLayers()
            app.setPalette(original_palette)
            if app.style().objectName() != original_style:
                app.setStyle(original_style)
        result["seconds"] = round(time.monotonic() - started, 3)
        results.append(result)
        (args.output / "ui-results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{'PASS' if result['passed'] else 'FAIL'} {name}: {result.get('detail', result.get('error', ''))}", flush=True)

    def fixtures(panel, entries):
        panel.search_timer.stop()
        panel.tree_widget.clear()
        panel.search_results_root = QTreeWidgetItem(panel.tree_widget)
        panel.search_results_root.setText(0, "Resultados de prueba")
        panel.favorites_root = QTreeWidgetItem(panel.tree_widget)
        panel.favorites_root.setText(0, "Favoritos")
        nodes = []
        for entry in entries:
            node = QTreeWidgetItem(panel.search_results_root)
            node.setText(0, entry["name"])
            node.setData(0, Qt.ItemDataRole.UserRole, dict(entry))
            nodes.append(node)
        panel.search_results_root.setExpanded(True)
        return nodes

    def layer(name, suffix="0"):
        return {"type": "arcgis_vector_layer", "stype": "arcgisfeatureserver", "name": name,
                "url": "https://example.test/rest/services/map/FeatureServer/" + suffix,
                "service_url": "https://example.test/rest/services/map/FeatureServer",
                "category": "Geología y Minería", "institution": "Fixture"}

    def select(panel, nodes):
        panel.tree_widget.clearSelection()
        for node in nodes:
            panel.tree_widget.scrollToItem(node)
            rect = panel.tree_widget.visualItemRect(node)
            QTest.mouseClick(panel.tree_widget.viewport(), Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.ControlModifier, rect.center())

    def search_is_local(c):
        calls = []
        c.panel.load_dynamic_node = lambda item: calls.append(item.text(0))
        c.panel.search_input.setFocus()
        QTest.keyClicks(c.panel.search_input, "expandir")
        QTest.qWait(250)
        assert not calls, f"Typing expanded remote nodes: {calls}"
        return "Typing placeholder text issued no remote loads"

    run_case("search_no_implicit_requests", search_is_local)

    def category(c):
        c.panel.category_combo.setCurrentText("Medio Ambiente")
        QTest.qWait(250)
        root = c.panel.tree_widget.topLevelItem(1)
        unexpected = []
        for index in range(root.childCount()):
            node = root.child(index)
            data = node.data(0, Qt.ItemDataRole.UserRole)
            if data["category"] != "Medio Ambiente" and not node.isHidden():
                unexpected.append(node.text(0))
        assert not unexpected, unexpected
        return "Unloaded placeholders do not defeat category filtering"

    run_case("category_hides_other_sources", category)

    def search_and_clear(c):
        c.panel.search_input.setFocus()
        QTest.keyClicks(c.panel.search_input, "geologia ingemmet")
        QTest.qWait(250)
        count = c.panel.search_results_root.childCount()
        assert 0 < count <= 200
        for index in range(count):
            node = c.panel.search_results_root.child(index)
            assert node.data(0, Qt.ItemDataRole.UserRole)["institution"].startswith("INGEMMET")
        QTest.keyClick(c.panel.search_input, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(c.panel.search_input, Qt.Key.Key_Backspace)
        QTest.qWait(250)
        assert c.panel.search_results_root.isHidden()
        assert not c.panel.btn_add_layer.isEnabled()
        return {"matches": count}

    run_case("keyboard_search_clear", search_and_clear)

    def mixed_selection(c):
        folder = dict(layer("Carpeta"), type="folder", stype="arcgis_rest", is_loaded=True)
        nodes = fixtures(c.panel, [folder, layer("A", "1"), layer("B", "2")])
        select(c.panel, nodes)
        assert len(c.panel.tree_widget.selectedItems()) == 3
        assert c.panel.btn_add_layer.isEnabled(), c.panel.btn_add_layer.text()
        assert "2" in c.panel.btn_add_layer.text()
        return "Two selected layers remain actionable alongside a folder"

    run_case("mixed_selection_button", mixed_selection)

    def batch(c, mode):
        nodes = fixtures(c.panel, [layer("A", "1"), layer("B", "2")])
        select(c.panel, nodes)
        created = []
        def instantiate(data):
            created.append(data["name"])
            return QgsVectorLayer("Point?crs=EPSG:4326", data["name"], "memory"), []
        c.panel._instantiate_layer = instantiate
        if mode == "search":
            QTimer.singleShot(0, c.panel.apply_catalog_search)
        elif mode == "reentrant":
            QTimer.singleShot(0, lambda: QTest.mouseClick(c.panel.btn_add_layer, Qt.MouseButton.LeftButton))
        elif mode == "rebuild":
            QTimer.singleShot(0, c.panel.populate_tree)
        elif mode == "unload":
            def unload():
                c.panel.cancel_background_tasks()
                c.window.removeDockWidget(c.panel)
                c.panel.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QTimer.singleShot(0, unload)
        c.panel.add_selected_layer()
        expected = 0 if mode == "unload" else 2
        assert len(QgsProject.instance().mapLayers()) == expected, created
        assert QApplication.overrideCursor() is None
        return {"loaded": len(created)}

    run_case("batch_search_during_load", lambda c: batch(c, "search"))
    run_case("batch_rebuild_during_load", lambda c: batch(c, "rebuild"))
    run_case("batch_reentrant_click", lambda c: batch(c, "reentrant"))
    run_case("batch_unload_during_events", lambda c: batch(c, "unload"))

    def favorite_wms(c):
        one = {"type": "wms_layer", "stype": "wms", "name": "Same title",
               "url": "https://example.test/wms", "service_url": "https://example.test/wms", "layer_name": "one"}
        two = dict(one, layer_name="two")
        nodes = fixtures(c.panel, [one, two])
        c.panel.add_to_favorites(nodes[0])
        c.panel.add_to_favorites(nodes[1])
        assert len(c.panel.load_favorites()) == 2
        return "Layer identity, not display title, distinguishes WMS favourites"

    run_case("favorite_wms_same_title", favorite_wms)

    def favorite_alias(c):
        one = layer("Original")
        nodes = fixtures(c.panel, [one, dict(one, name="Renamed")])
        for node in nodes:
            c.panel.add_to_favorites(node)
        assert len(c.panel.load_favorites()) == 1
        return "An alias does not duplicate the same ArcGIS layer"

    run_case("favorite_alias_deduplication", favorite_alias)

    def native_wms(c):
        name = "UI QA WMS"
        url = "https://example.test/wms?map=peru"
        c.panel.write_connection(name, url, "wms")
        names = QgsOwsConnection.connectionList("WMS")
        assert name in names, names
        assert QgsOwsConnection("WMS", name).uri().param("url") == url
        return "Registered connection is visible to QGIS native OWS API"

    run_case("native_browser_wms_registration", native_wms)

    def connection_collision(c):
        c.panel.write_connection("Shared", "https://example.test/old", "wms", "test000")
        renamed = c.panel.write_connection("Shared", "https://example.test/new", "wms")
        assert QgsOwsConnection("WMS", "Shared").uri().param("url") == "https://example.test/old"
        assert renamed != "Shared"
        assert QgsOwsConnection("WMS", renamed).uri().param("url") == "https://example.test/new"
        return "An unrelated existing connection is not silently overwritten"

    run_case("connection_name_collision", connection_collision)

    def preserve_auth(c):
        url = "https://example.test/auth"
        c.panel.write_connection("Protected", url, "wms", "test000")
        c.panel.write_connection("Protected", url, "wms")
        assert QgsOwsConnection("WMS", "Protected").uri().authConfigId() == "test000"
        return "Registering an existing URL does not erase its authentication"

    run_case("connection_preserves_authcfg", preserve_auth)

    def slash_name(c):
        c.panel.write_connection("UI QA / Slashes", "https://example.test/slash", "wms")
        names = QgsOwsConnection.connectionList("WMS")
        found = [name for name in names if QgsOwsConnection("WMS", name).uri().param("url") == "https://example.test/slash"]
        assert found, names
        return found

    run_case("connection_name_with_slash", slash_name)

    def malformed_auth(c):
        QgsSettings().setValue(c.panel.AUTH_SCOPES_SETTINGS_KEY, '{"https://example.test":null,"https://other.test":false}')
        assert c.panel.load_auth_scopes() == {}
        return "Malformed auth configuration values are discarded"

    run_case("malformed_auth_scopes", malformed_auth)

    def wait_until(predicate, timeout=6000):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert predicate(), "Background operation did not finish"

    def anonymous_scope(c):
        parent = "https://example.test/rest/services"
        child = parent + "/Public"
        c.panel.auth_scopes = {parent: "test000", child: c.panel.NO_AUTH_SCOPE}
        assert c.panel.auth_config_for_url(parent + "/Private/MapServer") == "test000"
        assert c.panel.auth_config_for_url(child + "/MapServer") == ""
        assert c.panel.auth_config_for_url(parent + "Elsewhere") == ""
        c.panel.write_connection("Anonymous override", child, "arcgis_rest", "test000")
        c.panel.write_connection("Anonymous override", child, "arcgis_rest")
        from peru_ui_checks.peruspatial_hub_connections import connection_root
        key = connection_root("arcgis_rest") + "/Anonymous override/authcfg"
        assert QgsSettings().value(key) == ""
        return "Most specific anonymous scope clears saved auth without matching sibling paths"

    run_case("explicit_anonymous_scope", anonymous_scope)

    def partial_failure(c):
        nodes = fixtures(c.panel, [layer("Good"), layer("Broken", "1")])
        select(c.panel, nodes)
        def instantiate(data):
            if data["name"] == "Broken":
                raise RuntimeError("Controlled provider failure")
            return QgsVectorLayer("Point?crs=EPSG:4326", "Good", "memory"), []
        c.panel._instantiate_layer = instantiate
        c.panel.add_selected_layer()
        assert len(QgsProject.instance().mapLayers()) == 1
        assert any("Controlled provider failure" in str(dialog) for dialog in c.dialogs), c.dialogs
        assert c.panel.btn_add_layer.isEnabled()
        assert not c.panel.progress_bar.isVisible()
        assert QApplication.overrideCursor() is None
        return "Partial failures retain successful layers and report the failing provider"

    run_case("partial_batch_failure", partial_failure)

    def background_health(c, overlap=False, unload=False):
        import threading
        gate, entered = threading.Event(), threading.Event()
        base = {"institution": "Fixture", "name": "Fixture", "category": "Geología y Minería"}
        c.panel.live_servers = [dict(base, stype="arcgis_rest", url="https://example.test/good"),
            dict(base, stype="arcgis_rest", url="https://example.test/bad"),
            dict(base, stype="wms", url="https://example.test/html")]
        def fetch(url, **kwargs):
            entered.set()
            if not gate.wait(5):
                raise RuntimeError("Fixture gate timed out")
            return {"services": []} if url.endswith("good") else {"error": {"message": "Denied"}}
        c.panel.fetch_arcgis_json = fetch
        c.panel.read_service_https = lambda *a, **kw: b"<html>Upstream failure</html>"
        reports = []
        c.panel.show_health_results = reports.append
        c.panel.check_all_servers_health()
        task_refs = list(c.panel._background_tasks)
        try:
            wait_until(entered.is_set)
            c.panel.check_all_servers_health()
            assert len(c.panel._background_tasks) == 1, "Repeated health check started a duplicate task"
            if overlap:
                c.panel._loading_layers = True
                c.panel._layer_progress = (1, 3, "Layer progress fixture")
                c.panel._update_progress()
            if unload:
                c.panel.cancel_background_tasks()
                c.window.removeDockWidget(c.panel)
                c.panel.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            gate.set()
            wait_until(lambda: not c.panel._background_tasks)
            if unload:
                wait_until(lambda: not any(task in QgsApplication.taskManager().activeTasks() for task in task_refs))
                QTest.qWait(100)
                assert not reports
                return "Real background task cancelled while its panel is deleted"
            assert len(reports) == 1 and [row[1] for row in reports[0]] == [True, False, False], reports
            assert c.panel.btn_health_check.isEnabled()
            if overlap:
                assert c.panel.progress_bar.isVisible()
                assert c.panel.progress_bar.maximum() == 3
                assert c.panel.progress_bar.value() == 1
                assert c.panel.progress_bar.format() == "Layer progress fixture"
                c.panel._loading_layers = False
                c.panel._update_progress()
            assert not c.panel.progress_bar.isVisible()
            return "Real task reports valid REST, invalid REST and HTML WMS correctly"
        finally:
            gate.set()

    run_case("background_health_validation", background_health)
    run_case("concurrent_health_layer_progress", lambda c: background_health(c, overlap=True))
    run_case("background_task_after_unload", lambda c: background_health(c, unload=True))

    def lazy_crs_warning(c):
        root_data = dict(layer("Root"), type="server", stype="arcgis_rest", crs_warning=True, is_loaded=False)
        root = fixtures(c.panel, [root_data])[0]
        def fetch(url, **kwargs):
            if url.endswith("FeatureServer"):
                return {"layers": [{"id": 0, "name": "Leaf", "type": "Feature Layer", "parentLayerId": -1}]}
            if url.endswith("/Folder"):
                return {"services": [{"name": "Folder/Service", "type": "FeatureServer"}]}
            return {"folders": ["Folder"], "services": []}
        c.panel.fetch_arcgis_json = fetch
        current = root
        for expected_type in ("folder", "arcgis_service", "arcgis_vector_layer"):
            c.panel.load_dynamic_node(current)
            wait_until(lambda: not c.panel._background_tasks)
            current = current.child(0)
            assert current is not None
            data = current.data(0, Qt.ItemDataRole.UserRole)
            assert data and data["type"] == expected_type, data
            assert data.get("crs_warning"), f"CRS warning lost at {expected_type}"
        select(c.panel, [current])
        assert c.panel.crs_banner.isVisible()
        return "Source CRS warning survives folder, service and leaf discovery"

    run_case("lazy_crs_warning_inheritance", lazy_crs_warning)

    def context_target(c):
        from qgis.PyQt.QtWidgets import QMenu
        nodes = fixtures(c.panel, [layer("First"), layer("Second", "2")])
        select(c.panel, [nodes[0]])
        original_exec = QMenu.exec
        observed = []
        def invoke(menu, *args):
            for action in menu.actions():
                if action.text() == "Copiar URL":
                    observed.append(action.text())
                    action.trigger()
        QMenu.exec = invoke
        try:
            rect = c.panel.tree_widget.visualItemRect(nodes[1])
            c.panel.show_context_menu(rect.center())
            assert observed
            assert QApplication.clipboard().text() == layer("Second", "2")["url"]
        finally:
            QMenu.exec = original_exec
        return "Context menu operates on the clicked row"

    run_case("context_menu_target", context_target)

    def stale_task(c):
        import threading
        entered, release = threading.Event(), threading.Event()
        data = dict(layer("Root"), type="server", stype="arcgis_rest", is_loaded=False)
        root = fixtures(c.panel, [data])[0]
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Fixture gate timed out")
                return {"folders": ["Stale"], "services": []}
            return {"folders": ["Current"], "services": []}
        c.panel.fetch_arcgis_json = fetch
        c.panel.load_dynamic_node(root)
        try:
            wait_until(entered.is_set)
            c.panel.refresh_node(root)
            wait_until(lambda: root.childCount() == 1 and root.child(0).text(0) == "Current")
            release.set()
            wait_until(lambda: not c.panel._background_tasks)
            assert root.childCount() == 1 and root.child(0).text(0) == "Current"
        finally:
            release.set()
        return "A late pre-refresh response cannot replace fresh directory content"

    run_case("stale_directory_task", stale_task)

    def favorite_remove(c):
        node = fixtures(c.panel, [layer("Saved")])[0]
        c.panel.add_to_favorites(node)
        c.panel.populate_tree()
        assert c.panel.favorites_root.childCount() == 1
        saved = c.panel.favorites_root.child(0)
        assert saved.data(0, Qt.ItemDataRole.UserRole)["url"] == layer("Saved")["url"]
        c.panel.remove_from_favorites(saved)
        c.panel.populate_tree()
        assert not c.panel.load_favorites()
        assert all(c.panel.favorites_root.child(i).data(0, Qt.ItemDataRole.UserRole) is None
                   for i in range(c.panel.favorites_root.childCount()))
        return "Favorite survives tree rebuild and is removed persistently"

    run_case("favorite_persistence_and_remove", favorite_remove)

    def multi_context(c):
        from qgis.PyQt.QtWidgets import QMenu
        nodes = fixtures(c.panel, [layer("First"), layer("Second", "2")])
        select(c.panel, nodes)
        original = QMenu.exec
        states = {}
        def inspect(menu, *args):
            states.update({action.text(): action.isEnabled() for action in menu.actions() if action.text()})
        QMenu.exec = inspect
        try:
            c.panel.show_context_menu(c.panel.tree_widget.visualItemRect(nodes[0]).center())
        finally:
            QMenu.exec = original
        assert states.get("Añadir 2 capas al Mapa") is True, states
        assert states.get("Copiar URL") is False and states.get("Abrir en navegador") is False, states
        return "Multiple selection offers batch loading and disables ambiguous single-resource actions"

    run_case("multiple_selection_context_actions", multi_context)

    def inventory_metadata_details(c):
        entry = dict(layer("Metadata fixture"), geometry_type="esriGeometryPolygon", field_count=12,
                     spatial_reference={"wkid": 102100, "latestWkid": 3857}, metadata_warnings=["duplicate_field_names"])
        node = fixtures(c.panel, [entry])[0]
        select(c.panel, [node])
        text = c.panel.metadata_panel.toPlainText()
        assert "Polígonos" in text and "12 campos publicados" in text and "3857" in text, text
        assert "nombres de campos repetidos" in text
        table = dict(layer("Table fixture"), is_table=True, data_kind="tabla", field_count=4)
        node = fixtures(c.panel, [table])[0]
        select(c.panel, [node])
        assert "Tabla sin geometría" in c.panel.metadata_panel.toPlainText()
        assert "CRS declarado" not in c.panel.metadata_panel.toPlainText()
        return "Published schema, CRS identifiers and upstream field warnings are visible without inventing a table CRS"

    run_case("inventory_metadata_details", inventory_metadata_details)

    def mapserver_raster_choices(c):
        c.panel.populate_catalog_results("100k geologia", "Todas las Categorías")
        first = c.panel.search_results_root.child(0)
        assert c.panel.tree_widget.headerItem().text(1) == "Tipo de dato"
        assert c.panel.tree_widget.headerItem().text(2) == "Fuente"
        assert first.text(1) == "Ráster" and first.text(2) == "MapServer"
        service = dict(layer("SERV_GEOLOGIA_100K"), type="arcgis_service", service_kind="MapServer",
                       stype="arcgis_mapserver", url="https://example.test/rest/services/geologia/MapServer")
        node = fixtures(c.panel, [service])[0]
        select(c.panel, [node])
        assert c.panel.btn_add_layer.isEnabled() and c.panel.btn_add_layer.text() == "Añadir mapa ráster"
        assert c.panel.entry_display_type(service) == "Ráster"
        calls = []
        def raster(url, layer_id, name, metadata=None):
            calls.append((url, layer_id))
            return QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")
        c.panel.create_arcgis_map_layer = raster
        rendered, errors = c.panel._instantiate_layer(service)
        assert rendered.isValid() and not errors and calls == [(service["url"], None)]
        leaf = dict(service, type="arcgis_map_layer", service_url=service["url"], layer_id=7,
                    url=service["url"] + "/7", prefer_raster=True)
        c.panel.fetch_arcgis_json = lambda *a, **kw: {"id": 7, "type": "Feature Layer", "geometryType": "esriGeometryPolygon", "capabilities": "Query"}
        c.panel.create_arcgis_vector_layer = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Raster choice must not construct a vector"))
        rendered, errors = c.panel._instantiate_layer(leaf)
        assert rendered.isValid() and not errors and calls[-1] == (service["url"], 7)
        return "Full MapServer loads as raster; an explicit raster choice bypasses vector loading"

    run_case("mapserver_raster_choices", mapserver_raster_choices)

    def tree_scroll_and_splitter(c):
        c.panel.populate_catalog_results("geologia", "Todas las Categorías")
        node = c.panel.search_results_root.child(0)
        select(c.panel, [node])
        original = dict(node.data(0, Qt.ItemDataRole.UserRole))
        c.panel.splitter.setSizes([1, 2000])
        app.processEvents()
        assert c.panel.tree_widget.height() >= 120, f"Tree collapses to {c.panel.tree_widget.height()} px"
        assert not node.icon(0).isNull(), "Service folders need a visible folder icon"
        c.panel.splitter.setSizes([440, 210])
        c.panel.tree_widget.setColumnWidth(1, 350)
        horizontal = c.panel.tree_widget.horizontalScrollBar()
        vertical = c.panel.tree_widget.verticalScrollBar()
        for bar in (horizontal, vertical):
            bar.setValue(bar.maximum())
            app.processEvents()
            bar.setValue(0)
        assert node.data(0, Qt.ItemDataRole.UserRole) == original
        assert c.panel.tree_widget.currentItem() is node
        assert c.panel.metadata_panel.toPlainText().startswith(original["name"])
        return {"tree_minimum_height": c.panel.tree_widget.minimumHeight(), "rows": c.panel.search_results_root.childCount(),
                "selection_survives_scrolling": True}

    run_case("tree_scroll_and_splitter", tree_scroll_and_splitter)

    def expand_search_result_contents(c):
        service = dict(layer("SERV_GEOLOGIA"), type="arcgis_service", service_kind="MapServer",
                       stype="arcgis_mapserver", url="https://example.test/rest/services/SERV_GEOLOGIA/MapServer",
                       _catalog_result=True, is_loaded=False)
        c.panel.search_input.setText("SERV_GEOLOGIA")
        root = fixtures(c.panel, [service])[0]
        c.panel.set_item_metadata(root, service)
        QTreeWidgetItem(root).setText(0, "Expandir para consultar en vivo...")
        records = [{"id": 0, "name": "Unidades", "type": "Group Layer", "subLayerIds": [1], "parentLayerId": -1},
                   {"id": 1, "name": "Contactos", "type": "Feature Layer", "parentLayerId": 0,
                    "geometryType": "esriGeometryPolyline", "fields": []}]
        c.panel.fetch_arcgis_json = lambda *a, **kw: {"layers": records}
        select(c.panel, [root])
        QTest.keyClick(c.panel.tree_widget, Qt.Key.Key_Right)
        wait_until(lambda: not c.panel._background_tasks)
        group = root.child(0)
        assert root.isExpanded() and group.text(0) == "Unidades" and not group.isHidden()
        select(c.panel, [group])
        QTest.keyClick(c.panel.tree_widget, Qt.Key.Key_Right)
        leaf = group.child(0)
        assert not leaf.isHidden() and leaf.text(0) == "Contactos"
        assert leaf.text(1) == "Vectorial" and leaf.text(2) == "MapServer"
        assert not group.icon(0).isNull() and not leaf.icon(0).isNull()
        root.setExpanded(False)
        c.panel.filter_services()
        assert not root.isExpanded(), "Filtering must respect an explicitly collapsed result"
        c.panel.tree_widget.scrollToItem(root)
        QTest.mouseClick(c.panel.tree_widget.viewport(), Qt.MouseButton.LeftButton,
                        pos=c.panel.tree_widget.visualItemRect(root).center())
        QTest.mouseDClick(c.panel.tree_widget.viewport(), Qt.MouseButton.LeftButton,
                         pos=c.panel.tree_widget.visualItemRect(root).center())
        assert root.isExpanded(), "A double click must expand once rather than toggle twice"
        return "Expanding a matched service exposes its folders and layers even when their names do not repeat the search"

    run_case("expand_search_result_contents", expand_search_result_contents)

    def invalid_service_inventory(c):
        entry = dict(layer("Cyclic service"), type="arcgis_service", stype="arcgis_mapserver",
                     service_kind="MapServer", url="https://example.test/rest/services/Test/MapServer", is_loaded=False)
        root = fixtures(c.panel, [entry])[0]
        c.panel.fetch_arcgis_json = lambda *a, **kw: {"layers": [
            {"id": 1, "name": "A", "parentLayerId": 2}, {"id": 2, "name": "B", "parentLayerId": 1}]}
        c.panel.load_dynamic_node(root)
        wait_until(lambda: not c.panel._background_tasks)
        assert not root.data(0, Qt.ItemDataRole.UserRole)["is_loaded"]
        assert root.childCount() == 1 and "ciclo" in root.child(0).text(0)
        return "Cyclic service hierarchy produces a retryable error instead of recursively constructing Qt nodes"

    run_case("invalid_service_inventory", invalid_service_inventory)

    def full_service_inventory(c, broken=False):
        entry = dict(layer("Full inventory"), type="arcgis_service", stype="arcgis_featureserver",
                     service_kind="FeatureServer", url="https://example.test/rest/services/Test/FeatureServer", is_loaded=False)
        root = fixtures(c.panel, [entry])[0]
        leaf = {"id": 0, "name": "Listed", "type": "Feature Layer", "parentLayerId": -1, "fields": []}
        extra = {"id": 1, "name": "Bulk only", "type": "Feature Layer", "parentLayerId": -1,
                 "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}], "geometryType": "esriGeometryPolygon"}
        group = {"id": 0, "name": "Broken group", "type": "Group Layer", "parentLayerId": -1, "subLayerIds": [127]}
        requested = []
        def fetch(url, **kwargs):
            requested.append(url)
            if url == entry["url"]:
                return {"layers": [group if broken else leaf]}
            if url.endswith("/layers"):
                return {"layers": [dict(group, subLayers=[{"id": -1}])] if broken else [leaf, extra]}
            if not broken and url.endswith("/1"):
                return extra
            raise ValueError("Missing published child")
        c.panel.fetch_arcgis_json = fetch
        c.panel.load_dynamic_node(root)
        wait_until(lambda: not c.panel._background_tasks)
        assert root.data(0, Qt.ItemDataRole.UserRole)["is_loaded"]
        if broken:
            assert root.childCount() == 1 and root.child(0).childCount() == 0
            select(c.panel, [root])
            assert "incomplete_sublayers" in root.data(0, Qt.ItemDataRole.UserRole)["metadata_warnings"]
            assert not any(url.endswith("/-1") for url in requested)
        else:
            assert root.childCount() == 2
            node = next(root.child(i) for i in range(root.childCount()) if "Bulk only" in root.child(i).text(0))
            select(c.panel, [node])
            assert "1 campo publicado" in c.panel.metadata_panel.toPlainText()
            assert entry["url"] + "/1" in requested
        return {"broken_references": broken, "requests": len(requested), "children": root.childCount()}

    run_case("bulk_only_verified_layer", full_service_inventory)
    run_case("broken_group_no_phantom_layers", lambda c: full_service_inventory(c, broken=True))

    def obsolete_group_id(c):
        entry = dict(layer("Old cached name"), type="arcgis_map_layer", service_kind="MapServer", layer_id=6)
        c.panel.fetch_arcgis_json = lambda *a, **kw: {"id": 6, "name": "New group", "type": "Group Layer"}
        constructed = []
        c.panel.create_arcgis_map_layer = lambda *a, **kw: constructed.append("raster")
        result, errors = c.panel._instantiate_layer(entry)
        assert result is None and not constructed and any("grupo" in error for error in errors)
        c.panel.fetch_arcgis_json = lambda *a, **kw: {"id": 6, "name": "Table", "type": "Table", "fields": []}
        c.panel.create_arcgis_vector_layer = lambda *a, **kw: QgsVectorLayer("None?field=id:integer", "Table", "memory")
        result, errors = c.panel._instantiate_layer(entry)
        assert result.isValid() and not result.isSpatial() and not constructed
        return "An outdated cached layer ID cannot render a repurposed group; published tables use the vector provider"

    run_case("obsolete_group_id_and_table_routing", obsolete_group_id)

    def published_crs(c):
        from qgis.core import QgsCoordinateReferenceSystem
        target = QgsCoordinateReferenceSystem("EPSG:32718")
        memory = QgsVectorLayer("Point", "Custom CRS", "memory")
        memory.setCrs(QgsCoordinateReferenceSystem())
        c.panel.apply_metadata_crs(memory, {"spatialReference": {"wkt": target.toWkt()}})
        assert memory.crs() == target
        original = QgsCoordinateReferenceSystem("EPSG:4326")
        memory.setCrs(original)
        c.panel.apply_metadata_crs(memory, {"spatialReference": {"wkt": target.toWkt()}})
        assert memory.crs() == original, "A valid provider CRS must never be relabelled"
        service = dict(layer("PSAD56 fixture"), type="arcgis_service", stype="arcgis_mapserver",
                       service_kind="MapServer", is_loaded=True, crs_warning=False)
        root = fixtures(c.panel, [service])[0]
        c.panel.populate_arcgis_service_layers(root, service, {"spatialReference": {"wkid": 4248},
            "layers": [{"id": 0, "name": "Declared vector", "type": "Feature Layer", "parentLayerId": -1}]})
        root.setExpanded(True)
        leaf = root.child(0)
        assert leaf.text(1) == "Vectorial"
        assert leaf.text(2) == "MapServer"
        select(c.panel, [leaf])
        assert c.panel.crs_banner.isVisible()
        return "Declared WKT recovers a missing CRS; valid CRS stays intact; explicit PSAD56 gets the datum notice"

    run_case("published_crs_wkt_and_datum_warning", published_crs)

    def network_policy(c):
        from qgis.core import Qgis, QgsNetworkAccessManager
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtNetwork import QNetworkRequest
        from peru_ui_checks import peruspatial_hub_network as network
        NetworkCompatibility, prepare_request = network.NetworkCompatibility, network.prepare_request
        url = "https://idesep.senamhi.gob.pe/geoserver/g_06_13/wms"
        def request(target=url):
            value = QNetworkRequest(QUrl(target))
            value.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, True)
            return value
        guard = NetworkCompatibility()
        try:
            guard.install()
            installed_id = guard.processor_id
            guard.install()
            assert guard.processor_id == installed_id
            matched = request()
            QgsNetworkAccessManager.instance().preprocessRequest(matched)
            native_hook_available = Qgis.QGIS_VERSION_INT >= 34400
            assert bool(guard.processor_id) == native_hook_available
            assert matched.attribute(QNetworkRequest.Attribute.Http2AllowedAttribute) is (not native_hook_available)
            other = request("https://example.test/geoserver/wms")
            QgsNetworkAccessManager.instance().preprocessRequest(other)
            assert other.attribute(QNetworkRequest.Attribute.Http2AllowedAttribute) is True
            direct = request()
            prepare_request(direct)
            assert direct.attribute(QNetworkRequest.Attribute.Http2AllowedAttribute) is False
        finally:
            guard.uninstall()
        guard.uninstall()
        restored = request()
        QgsNetworkAccessManager.instance().preprocessRequest(restored)
        assert restored.attribute(QNetworkRequest.Attribute.Http2AllowedAttribute) is True
        original_qgis = network.Qgis
        try:
            network.Qgis = SimpleNamespace(QGIS_VERSION_INT=33404)
            legacy = NetworkCompatibility()
            legacy.install()
            assert legacy.processor_id is None, "Unsafe legacy Python binding must not be invoked"
        finally:
            network.Qgis = original_qgis
        return {"metadata_http1": True, "native_provider_hook": native_hook_available,
                "other_hosts_unchanged": True, "unload_restores_policy": True, "legacy_binding_avoided": True}

    run_case("network_compatibility_scope_and_lifecycle", network_policy)

    def dialogs(c):
        for dialog in (ui.AboutDialog(c.window, str(args.plugin_root)),
                       ui.ServiceStatusDialog(c.window, c.panel.catalog_data),
                       ui.ServiceAccessDialog("Fixture", "https://example.test", parent=c.window)):
            dialog.show()
            app.processEvents()
            assert dialog.width() > 0 and dialog.height() > 0
            dialog.grab().save(str(args.output / (dialog.__class__.__name__ + ".png")))
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            app.processEvents()
            assert not dialog.isVisible()
            dialog.deleteLater()
        return "About, source status and private-access dialogs open and cancel"

    run_case("dialogs_and_keyboard_cancel", dialogs)

    def layout(c, width, font_size, dark):
        font = QFont(c.panel.font())
        font.setPointSize(font_size)
        c.panel.setFont(font)
        if dark:
            palette = QPalette(c.panel.palette())
            palette.setColor(QPalette.ColorRole.Window, QColor("#20252b"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#eceff4"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#eceff4"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#161a20"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#292f37"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#eceff4"))
            app.setStyle("Fusion")
            app.setPalette(palette)
            c.window.setPalette(palette)
            c.panel.setPalette(palette)
            c.panel.init_panel_style()
        c.window.resize(width, 850)
        QTest.qWait(50)
        content = c.panel.main_widget.rect()
        controls = [c.panel.search_input, c.panel.category_combo, c.panel.btn_service_status,
                    c.panel.btn_add_layer, c.panel.btn_register_browser, c.panel.tools_button]
        for control in controls:
            point = control.mapTo(c.panel.main_widget, control.rect().bottomRight())
            assert content.contains(point), f"Control clipped: {control.text() if hasattr(control, 'text') else control.objectName()}"
        header = c.panel.main_layout.itemAt(0).widget()
        header.grab().save(str(args.output / f"header-{width}-{font_size}-{'dark' if dark else 'light'}.png"))
        return {"requested_width": width, "actual_width": c.window.width(), "font": font_size, "dark": dark}

    run_case("layout_narrow", lambda c: layout(c, 330, 10, False))
    run_case("layout_large_font", lambda c: layout(c, 480, 16, False))
    run_case("layout_dark", lambda c: layout(c, 480, 11, True))

    if args.live:
        def live_health(c):
            reports = []
            show_results = c.panel.show_health_results
            def capture(results):
                reports.extend({"institution": server["institution"], "name": server["name"],
                    "url": server["url"], "online": ok, "error": error} for server, ok, error in results)
                def dismiss():
                    dialog = QApplication.activeModalWidget()
                    if dialog and dialog.windowTitle() == "Estado de servidores":
                        dialog.grab().save(str(args.output / "live-health-dialog.png"))
                        dialog.accept()
                QTimer.singleShot(100, dismiss)
                show_results(results)
            c.panel.show_health_results = capture
            c.panel.btn_health_check.trigger()
            assert c.panel._health_check_running
            wait_until(lambda: not c.panel._background_tasks, timeout=360000)
            assert len(reports) == len(c.panel.live_servers), reports
            assert c.panel.btn_health_check.isEnabled() and not c.panel.progress_bar.isVisible()
            (args.output / "live-health-sources.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"online": sum(row["online"] for row in reports), "total": len(reports),
                    "unavailable": [row for row in reports if not row["online"]]}
        run_case("live_all_sources_health_action", live_health)
    sys.excepthook = old_hook
    failures = [result for result in results if not result["passed"]]
    print(json.dumps({"passed": len(results) - len(failures), "failed": len(failures)}, indent=2), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
