"""Seeded user journeys using real Qt widgets and QGIS background tasks.

Network delays/errors are local fixtures: this does not stress public servers.
"""

import random
import threading
import time


def run_user_stress(run_case, *, app, ui, fixtures, layer, select, wait_until, seed, iterations):
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import Qt, QTimer, QCoreApplication, QEvent
    from qgis.PyQt.QtTest import QTest
    from qgis.PyQt.QtWidgets import QTreeWidgetItem
    from qgis.core import QgsProject, QgsVectorLayer

    def service(name, suffix="0"):
        return dict(layer(name), type="arcgis_service", stype="arcgis_mapserver", service_kind="MapServer",
                    url=f"https://example.test/rest/services/Stress{suffix}/MapServer",
                    _catalog_result=True, is_loaded=False)

    def metadata(tag, groups=3, leaves=5):
        records = []
        for group in range(groups):
            parent = group * (leaves + 1)
            records.append({"id": parent, "name": f"Group {tag}-{group}", "type": "Group Layer",
                            "parentLayerId": -1, "subLayerIds": list(range(parent + 1, parent + leaves + 1))})
            records.extend({"id": parent + child, "name": f"Leaf {tag}-{group}-{child}",
                            "type": "Feature Layer", "geometryType": "esriGeometryPolygon",
                            "parentLayerId": parent, "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]}
                           for child in range(1, leaves + 1))
        return {"layers": records}

    def nodes(c, entries):
        result = fixtures(c.panel, entries)
        for node, entry in zip(result, entries):
            c.panel.set_item_metadata(node, dict(entry))
            if entry.get("type") == "arcgis_service":
                QTreeWidgetItem(node).setText(0, "Expand to browse")
        return result

    def clear_search(c):
        c.panel.search_input.clear()
        c.panel.search_timer.stop()

    def rapid_search(c):
        rng = random.Random(seed + 1)
        remote = []
        c.panel.load_dynamic_node = lambda item: remote.append(item.text(0))
        terms = ["geologia", "100k", "fallas", "agua", "", "áreas protegidas", "ninguna_coincidencia_987"]
        changes = iterations * 25
        for index in range(changes):
            c.panel.search_input.setText(rng.choice(terms))
            c.panel.category_combo.setCurrentIndex(rng.randrange(c.panel.category_combo.count()))
            if index % 20 == 0:
                QTest.qWait(195)
                assert c.panel.search_results_root.childCount() <= 200
        c.panel.category_combo.setCurrentIndex(0)
        c.panel.search_input.setText("100k geologia")
        QTest.qWait(220)
        first = c.panel.search_results_root.child(0)
        assert first is not None and first.text(1) == "Ráster" and first.text(2) == "MapServer"
        assert not remote and not c.panel._background_tasks, remote
        return {"seed": seed, "text_and_filter_changes": changes, "unexpected_network_requests": len(remote)}

    run_case("stress_rapid_search_and_filters", rapid_search)

    def repeat_folders(c):
        clear_search(c)
        root = nodes(c, [service("Repeated browsing")])[0]
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            return metadata("browse", groups=6, leaves=8)
        c.panel.fetch_arcgis_json = fetch
        root.setExpanded(True)
        wait_until(lambda: not c.panel._background_tasks)
        expected = root.childCount()
        rng = random.Random(seed + 2)
        for _ in range(iterations * 15):
            root.setExpanded(False)
            c.panel.filter_services()
            assert not root.isExpanded()
            root.setExpanded(True)
            group = root.child(rng.randrange(expected))
            group.setExpanded(not group.isExpanded())
            c.panel.filter_services()
            assert root.childCount() == 6 and group.childCount() == 8
            assert not group.isHidden() and not group.child(0).isHidden()
            assert not group.icon(0).isNull() and group.child(0).text(2) == "MapServer"
        assert len(calls) == 2, calls
        return {"folder_cycles": iterations * 15, "groups": 6, "layers": 48, "metadata_requests": len(calls)}

    run_case("stress_repeated_folder_browsing", repeat_folders)

    def replaced_search(c):
        for turn in range(iterations):
            entered, release = threading.Event(), threading.Event()
            entry = service(f"Old service {turn}", str(turn))
            c.panel.catalog_entries = [entry, dict(layer("Current result"), _catalog_result=True)]
            c.panel.search_input.setText("Old service")
            c.panel.search_timer.stop()
            root = nodes(c, [entry])[0]
            def fetch(url, **kwargs):
                if not url.endswith("/layers"):
                    entered.set()
                    if not release.wait(8):
                        raise RuntimeError("Delayed response gate timed out")
                return metadata("old", groups=1, leaves=1)
            c.panel.fetch_arcgis_json = fetch
            root.setExpanded(True)
            try:
                wait_until(entered.is_set)
                c.panel.search_input.setText("Current result")
                QTest.qWait(220)
                release.set()
                wait_until(lambda: not c.panel._background_tasks)
                result = c.panel.search_results_root.child(0)
                assert result and "Current result" in result.text(0)
                assert c.panel.search_results_root.childCount() == 1
                assert not result.childCount(), "A stale response attached folders to a new result"
            finally:
                release.set()
        return {"searches_replaced_during_response": iterations, "stale_response_overwrites": 0}

    run_case("stress_replace_search_during_load", replaced_search)

    def reopen_preserves_work(c):
        entry = service("Keep this service")
        c.panel.catalog_entries = [entry]
        c.panel.search_input.setText("Keep this")
        c.panel.search_timer.stop()
        c.panel.apply_catalog_search()
        root = c.panel.search_results_root.child(0)
        c.panel.fetch_arcgis_json = lambda *a, **kw: metadata("saved", groups=1, leaves=2)
        root.setExpanded(True)
        wait_until(lambda: not c.panel._background_tasks)
        group = root.child(0)
        group.setExpanded(True)
        selected = group.child(0)
        select(c.panel, [selected])
        for _ in range(iterations):
            c.panel.close()
            app.processEvents()
            assert not c.panel.isVisible()
            c.panel.show()
            QTest.qWait(220)
            assert root.treeWidget() is c.panel.tree_widget, "Reopening discarded the browsed service"
            assert root.isExpanded() and group.isExpanded()
            assert c.panel.tree_widget.currentItem() is selected, "Reopening lost the selected layer"
            assert c.panel.btn_add_layer.isEnabled()
        return {"close_reopen_cycles": iterations, "selection_and_expansion_preserved": True}

    run_case("stress_reopen_preserves_browsing", reopen_preserves_work)

    def retry_after_timeout(c):
        clear_search(c)
        root = nodes(c, [service("Intermittent server")])[0]
        failures = [True]
        attempts = []
        def fetch(url, **kwargs):
            attempts.append(url)
            if failures[0]:
                raise TimeoutError("Simulated connection timeout")
            return metadata("recovered", groups=1, leaves=2)
        c.panel.fetch_arcgis_json = fetch
        for _ in range(iterations):
            failures[0] = True
            c.panel.refresh_node(root)
            wait_until(lambda: not c.panel._background_tasks)
            assert not root.data(0, Qt.ItemDataRole.UserRole)["is_loaded"]
            assert "Error al cargar" in root.child(0).text(0)
            root.setExpanded(False)
            failures[0] = False
            root.setExpanded(True)
            wait_until(lambda: not c.panel._background_tasks)
            assert root.data(0, Qt.ItemDataRole.UserRole)["is_loaded"]
            assert root.childCount() == 1 and root.child(0).childCount() == 2
        return {"timeout_and_retry_cycles": iterations, "metadata_requests": len(attempts)}

    run_case("stress_timeout_then_user_retry", retry_after_timeout)

    def concurrent_services(c):
        clear_search(c)
        rng = random.Random(seed + 3)
        count = 8
        completed = 0
        for turn in range(iterations):
            entries = [service(f"Service {turn}-{i}", f"{turn}_{i}") for i in range(count)]
            roots = nodes(c, entries)
            gates = {entry["url"]: threading.Event() for entry in entries}
            def fetch(url, **kwargs):
                base = url.removesuffix("/layers")
                if not gates[base].wait(8):
                    raise RuntimeError("Concurrent response gate timed out")
                return metadata(base.split("/")[-2], groups=1, leaves=2)
            c.panel.fetch_arcgis_json = fetch
            try:
                for root in roots:
                    root.setExpanded(True)
                collapsed = {1, 3, 6}
                for index in collapsed:
                    roots[index].setExpanded(False)
                order = list(gates.values())
                rng.shuffle(order)
                for gate in order:
                    gate.set()
                    QTest.qWait(15)
                wait_until(lambda: not c.panel._background_tasks, timeout=12000)
                for index, root in enumerate(roots):
                    assert root.data(0, Qt.ItemDataRole.UserRole)["is_loaded"]
                    assert root.childCount() == 1
                    assert f"Stress{turn}_{index}" in root.child(0).text(0)
                    assert root.isExpanded() is (index not in collapsed)
                    completed += 1
            finally:
                for gate in gates.values():
                    gate.set()
        return {"rounds": iterations, "concurrent_services_per_round": count, "correctly_attached_responses": completed}

    run_case("stress_concurrent_service_responses", concurrent_services)

    def same_layer_two_places(c):
        clear_search(c)
        entry = layer("One dataset")
        original = nodes(c, [entry])[0]
        c.panel.add_to_favorites(original)
        c.panel.favorites_root.setExpanded(True)
        favorite = c.panel.favorites_root.child(0)
        select(c.panel, [original, favorite])
        calls = []
        def instantiate(data):
            calls.append(data["url"])
            return QgsVectorLayer("Point?crs=EPSG:4326", data["name"], "memory"), []
        c.panel._instantiate_layer = instantiate
        QTest.mouseClick(c.panel.btn_add_layer, Qt.MouseButton.LeftButton)
        assert len(QgsProject.instance().mapLayers()) == 1, "Selecting a result and its favorite added the same dataset twice"
        assert len(calls) == 1
        return {"selected_locations": 2, "unique_datasets_added": 1}

    run_case("stress_same_layer_result_and_favorite", same_layer_two_places)

    def keyboard_add(c):
        clear_search(c)
        root = nodes(c, [layer("Keyboard dataset")])[0]
        select(c.panel, [root])
        c.panel._instantiate_layer = lambda data: (QgsVectorLayer("Point?crs=EPSG:4326", data["name"], "memory"), [])
        QTest.keyClick(c.panel.tree_widget, Qt.Key.Key_Return)
        assert len(QgsProject.instance().mapLayers()) == 1, "Enter did not add the selected layer"
        return "Keyboard activation adds the selected dataset once"

    run_case("stress_keyboard_activate_layer", keyboard_add)

    def favorite_churn(c):
        clear_search(c)
        count = 24
        entries = [dict(layer(f"Repeated title {index % 3}", str(index)), data_kind="vectorial") for index in range(count // 2)]
        entries.extend(dict(layer(f"Repeated title {index % 3}"), type="wms_layer", stype="wms",
                            service_url="https://example.test/wms?map=public", url="https://example.test/wms?map=public",
                            layer_name=f"namespace:layer_{index}", crs_options=["EPSG:4326"])
                       for index in range(count // 2))
        originals = nodes(c, entries)
        for node in originals:
            c.panel.add_to_favorites(node)
            c.panel.add_to_favorites(node)
        assert len(c.panel.load_favorites()) == count
        keys = {c.panel._favorite_key(entry) for entry in entries}
        for _ in range(iterations):
            c.panel.populate_tree()
            assert c.panel.favorites_root.childCount() == count
            for index in range(c.panel.favorites_root.childCount()):
                node = c.panel.favorites_root.child(index)
                assert node.text(1) in {"Ráster", "Vectorial"} and node.text(2) in {"WMS", "FeatureServer"}
                assert not node.icon(0).isNull()
            removed = c.panel.favorites_root.child(0)
            entry = dict(removed.data(0, Qt.ItemDataRole.UserRole))
            c.panel.remove_from_favorites(removed)
            assert len(c.panel.load_favorites()) == count - 1
            replacement = QTreeWidgetItem(c.panel.search_results_root)
            c.panel.set_item_metadata(replacement, entry)
            c.panel.add_to_favorites(replacement)
            assert {c.panel._favorite_key(item) for item in c.panel.load_favorites()} == keys
        assert all(not any(key.startswith("_") for key in entry) for entry in c.panel.load_favorites())
        return {"distinct_favorites_with_repeated_titles": count, "rebuild_remove_add_cycles": iterations,
                "internal_state_saved": False}

    run_case("stress_favorite_churn_and_rebuild", favorite_churn)

    def resize_and_redock(c):
        rng = random.Random(seed + 4)
        c.panel.search_input.setText("100k geologia")
        c.panel.search_timer.stop()
        c.panel.apply_catalog_search()
        root = c.panel.search_results_root.child(0)
        select(c.panel, [root])
        for turn in range(iterations * 2):
            c.window.resize(rng.choice([360, 480, 650, 900]), rng.choice([700, 850, 1000]))
            c.panel.splitter.setSizes(rng.choice([[1, 1000], [1000, 1], [440, 210]]))
            c.panel.setFloating(True)
            app.processEvents()
            c.panel.setFloating(False)
            c.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea if turn % 2 else Qt.DockWidgetArea.RightDockWidgetArea, c.panel)
            QTest.qWait(210)
            assert root.treeWidget() is c.panel.tree_widget and c.panel.tree_widget.currentItem() is root
            assert c.panel.tree_widget.height() >= 120
            assert c.panel.tree_widget.headerItem().text(2) == "Fuente"
            assert root.text(1) == "Ráster" and root.text(2) == "MapServer"
            assert c.panel.btn_add_layer.isEnabled()
        return {"resize_float_redock_cycles": iterations * 2, "selection_preserved": True}

    run_case("stress_resize_float_and_redock", resize_and_redock)

    def batch_with_changes(c):
        clear_search(c)
        count = iterations * 8
        entries = [layer(f"Dataset {index}", str(index)) for index in range(count)]
        chosen = nodes(c, entries)
        select(c.panel, chosen)
        calls = []
        def instantiate(data):
            index = int(data["url"].rsplit("/", 1)[1])
            calls.append(index)
            if index % 7 == 0:
                raise ConnectionError("Simulated provider failure")
            return QgsVectorLayer("Point?crs=EPSG:4326", data["name"], "memory"), []
        c.panel._instantiate_layer = instantiate
        QTimer.singleShot(0, lambda: c.panel.search_input.setText("new search while loading"))
        c.panel.add_selected_layer()
        expected = sum(index % 7 != 0 for index in range(count))
        assert len(calls) == count and len(QgsProject.instance().mapLayers()) == expected
        assert not c.panel._loading_layers and not c.panel.progress_bar.isVisible()
        assert len(c.dialogs) == 1, "Batch errors must be grouped in one message"
        return {"selected_datasets": count, "successful": expected, "failures": count - expected,
                "selection_changed_during_batch": True}

    run_case("stress_batch_partial_failures_and_search", batch_with_changes)

    def unload_pending_services(c):
        clear_search(c)
        release = threading.Event()
        started = threading.Event()
        roots = nodes(c, [service(f"Pending {i}", str(i)) for i in range(8)])
        def fetch(url, **kwargs):
            started.set()
            if not release.wait(8):
                raise RuntimeError("Unload gate timed out")
            return metadata("discarded", groups=1, leaves=1)
        c.panel.fetch_arcgis_json = fetch
        for root in roots:
            root.setExpanded(True)
        tasks = list(c.panel._background_tasks)
        try:
            wait_until(started.is_set)
            c.panel.cancel_background_tasks()
            c.window.removeDockWidget(c.panel)
            c.panel.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert sip.isdeleted(c.panel)
        finally:
            release.set()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and any(not sip.isdeleted(task) and task.isActive() for task in tasks):
            QTest.qWait(20)
        assert all(sip.isdeleted(task) or not task.isActive() for task in tasks)
        return {"pending_service_tasks": len(tasks), "late_callbacks_after_unload": "discarded"}

    run_case("stress_unload_with_pending_services", unload_pending_services)
