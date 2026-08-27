# -*- coding: utf-8 -*-
"""
Main controller class for the PeruSpatial Hub QGIS plugin.
Handles the plugin lifetime, GUI actions, menus, and dock panel loading.
"""

import os
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsSettings

# Import our panel
from .peruspatial_hub_panel import PeruSpatialHubPanel

class PeruSpatialHub(object):
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dock_widget = None

    def tr(self, message):
        """Get the translation for a string using Qt translation API."""
        return QCoreApplication.translate('PeruSpatialHub', message)

    def initGui(self):
        """Create the menu entries and toolbar icons of the plugin."""
        icon_path = os.path.join(self.plugin_dir, "logo_solo.png")
        icon = QIcon(icon_path)
        if icon.isNull():
            try:
                from qgis.core import QgsApplication
                icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")
            except Exception:
                icon = QIcon()

        self.action = QAction(
            icon,
            "PeruSpatial Hub",
            self.iface.mainWindow()
        )
        self.action.setStatusTip(self.tr("Explorar geoportales y servicios espaciales del Perú"))
        self.action.triggered.connect(self.run)

        # Add to Plugins menu and standard plugins toolbar (always visible)
        self.iface.addPluginToMenu("PeruSpatial Hub", self.action)
        self.iface.addToolBarIcon(self.action)

        # Automatically show dock panel on first run/installation
        settings = QgsSettings()
        if not settings.value("PeruSpatialHub/has_run_before", False, type=bool):
            self.run()
            settings.setValue("PeruSpatialHub/has_run_before", True)

    def unload(self):
        """Removes the plugin menu items and icon from QGIS GUI."""
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("PeruSpatial Hub", self.action)

        if self.dock_widget:
            self.dock_widget.cancel_background_tasks()
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def run(self):
        """Creates and shows the dock panel."""
        try:
            if not self.dock_widget:
                self.dock_widget = PeruSpatialHubPanel(self.iface, self.iface.mainWindow(), self.plugin_dir)
                self.iface.addDockWidget(
                    Qt.DockWidgetArea.RightDockWidgetArea, self.dock_widget
                )

            self.dock_widget.tree_widget.collapseAll()
            self.dock_widget.show()
            self.dock_widget.raise_()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error en PeruSpatial Hub",
                f"No se pudo abrir el panel del plugin.\n\nDetalle del error:\n{tb}"
            )
