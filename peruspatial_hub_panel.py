# -*- coding: utf-8 -*-
"""
Dockable panel UI for PeruSpatial Hub.
Constructed programmatically via PyQt5.
"""

import os
import webbrowser
import urllib.parse
import json
import time
from html import escape
from qgis.PyQt import sip

from qgis.PyQt.QtCore import Qt, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QPushButton, QToolButton,
    QLabel, QTextBrowser, QMessageBox, QSplitter, QDialog, QDialogButtonBox,
    QMenu, QProgressBar, QHeaderView
)
from qgis.PyQt.QtGui import QFont, QColor, QPalette, QIcon
from qgis.core import (
    QgsSettings, QgsRasterLayer, QgsVectorLayer, QgsProject, QgsDataSourceUri,
    QgsCoordinateReferenceSystem, QgsNetworkAccessManager, QgsApplication, QgsTask,
    QgsProviderRegistry,
)
from qgis.gui import QgsAuthConfigSelect

from .peruspatial_hub_urls import (
    append_rest_path as _append_rest_path,
    clean_rest_url as _clean_rest_url,
    service_url as _service_url,
    url_with_json as _url_with_json,
    wms_capabilities_url as _wms_capabilities_url,
    wms_service_url as _wms_service_url,
    favorite_identity,
)
from .peruspatial_hub_connections import register_connection, connection_root
from .peruspatial_hub_network import prepare_request
from .peruspatial_hub_ogc import merge_crs, parse_wms_layer_catalog
from .peruspatial_hub_catalog import (
    load_catalog,
    normalize_search_text as _normalize_catalog_text,
    search_catalog,
    arcgis_directory,
    arcgis_service_records,
    arcgis_data_kind,
    is_psad56_reference,
    resolve_arcgis_inventory,
    arcgis_metadata_fields,
)
from .peruspatial_hub_sources import (
    ACTIVE_REST_ROOTS,
    ACTIVE_WMS_ROOTS,
    CATALOG_CATEGORIES,
    LIVE_SERVERS,
)

ARCGIS_SERVICE_TYPES = {
    "arcgis_mapserver": "MapServer",
    "arcgisfeatureserver": "FeatureServer",
    "arcgis_imageserver": "ImageServer",
}

MAX_HTTP_RESPONSE_BYTES = 20 * 1024 * 1024


def _read_plugin_version():
    """Read the plugin version from metadata.txt at import time."""
    import configparser
    metadata_path = os.path.join(os.path.dirname(__file__), "metadata.txt")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(metadata_path, encoding="utf-8")
    return parser.get("general", "version", fallback="0.0.0")


PLUGIN_USER_AGENT = f"PeruSpatial-Hub-QGIS/{_read_plugin_version()}"



class AboutDialog(QDialog):
    def __init__(self, parent=None, plugin_dir=None):
        super().__init__(parent)
        self.setWindowTitle("Acerca de PeruSpatial Hub")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(12)
        title = QLabel("<h2>PeruSpatial Hub</h2>")
        layout.addWidget(title)
        version = QLabel(f"Versión {_read_plugin_version()} · Complemento para QGIS")
        layout.addWidget(version)
        description = QLabel("Acceso a servicios geoespaciales de instituciones públicas del Perú.")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(8)
        author = QLabel(
            "<b>Jordan Zavaleta</b> · GisGeo Dev<br>"
            "<a href='mailto:jordanzav@gisgeo.dev'>jordanzav@gisgeo.dev</a>"
        )
        author.setOpenExternalLinks(True)
        layout.addWidget(author)
        links = QLabel(
            "<a href='https://gisgeo.dev'>Sitio web</a> · "
            "<a href='https://www.linkedin.com/in/jordan-zav/'>LinkedIn</a> · "
            "<a href='https://github.com/jordan-zav/Peruspatial-Hub'>Código fuente</a>"
        )
        links.setOpenExternalLinks(True)
        layout.addWidget(links)
        layout.addSpacing(12)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ServiceStatusDialog(QDialog):
    """Explains why researched institutions may not appear in the catalog."""

    def __init__(self, parent=None, catalog_data=None):
        super().__init__(parent)
        self.setWindowTitle("Fuentes del catálogo")
        self.setMinimumSize(560, 430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(10)

        title = QLabel("<h2>Disponibilidad y acceso</h2>")
        layout.addWidget(title)

        details = QTextBrowser()
        details.setOpenExternalLinks(True)
        details.document().setDefaultStyleSheet(
            "h3 { margin-top: 16px; margin-bottom: 4px; } p { margin-top: 4px; }"
        )
        catalog_data = catalog_data or {}
        rows = []
        for source in catalog_data.get("sources", []):
            label = escape(f"{source.get('institution', '')} — {source.get('name', '')}")
            status = escape(str(source.get("status", "sin verificar")))
            checked = escape(str(source.get("checked_at") or catalog_data.get("generated_at", "sin fecha")))
            retained = int(source.get("retained_entries", 0))
            note = f"; {retained} entradas anteriores sin volver a verificar" if retained else ""
            rows.append(f"<li><b>{label}</b>: {status}{note}<br><small>{checked}</small></li>")
        details.setHtml(
            "<p>Notas de la revisión incluida en el catálogo. Para consultar la "
            "disponibilidad actual, use <b>Herramientas → Verificar servidores</b>.</p>"
            "<h3>OEFA</h3><p>El directorio público PIFA está integrado en el catálogo.</p>"
            "<h3>SUNARP</h3><p>El visor BGR requiere identificación y captcha. "
            "No se identificó un directorio REST de acceso anónimo.</p>"
            "<h3>Nuevos directorios públicos</h3><p>ANA/SNIRH, CENEPRED/SIGRID, "
            "MTC/Provías Nacional, MIDAGRI, SENACE y siete WMS temáticos de SENAMHI están incorporados. La disponibilidad "
            "del directorio no garantiza todas sus capas.</p>"
            "<h3>COFOPRI</h3><p>El endpoint evaluado presentó un problema de certificado "
            "TLS. No se desactivó la validación para registrarlo.</p>"
            "<h3>INEI y catálogo general SENAMHI</h3><p>Los endpoints generales evaluados "
            "no respondieron dentro del plazo de la auditoría. Esto no demuestra "
            "una baja permanente. Los WMS temáticos SENAMHI sí se verificaron e integraron.</p>"
            "<h3>Servicios con acceso privado</h3>"
            "<p>Seleccione un servicio HTTPS y use <b>Herramientas → Configurar acceso "
            "privado</b>. Las credenciales se administran en QGIS. La autenticación "
            "no resuelve fallas de disponibilidad ni permite omitir captchas.</p>"
            "<h3>Estado del inventario incluido</h3><ul>" + "".join(rows) + "</ul>"
        )
        layout.addWidget(details)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class ServiceAccessDialog(QDialog):
    """Selects or creates a credential set in QGIS' encrypted auth database."""

    def __init__(self, service_name, service_url, authcfg="", provider_key="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acceso privado al servicio")
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(10)

        title = QLabel(f"<h3>{escape(service_name)}</h3>")
        title.setWordWrap(True)
        layout.addWidget(title)

        explanation = QLabel(
            "Seleccione o cree una configuración de autenticación de QGIS para este servicio. "
            "Las credenciales se guardan cifradas en su perfil local."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        resource = QLabel(f"<b>Servicio</b><br>{escape(service_url)}")
        resource.setWordWrap(True)
        resource.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(resource)

        self.auth_selector = QgsAuthConfigSelect(self, provider_key)
        self.auth_selector.setConfigId(authcfg or "")
        layout.addWidget(self.auth_selector)

        note = QLabel(
            "Para dejar de usar credenciales en este servicio, seleccione "
            "Sin autenticación. Puede administrar o borrar definitivamente las "
            "credenciales desde el mismo selector de QGIS."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar acceso")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def config_id(self):
        return self.auth_selector.configId().strip()


class PeruSpatialHubPanel(QDockWidget):
    AUTH_SCOPES_SETTINGS_KEY = "PeruSpatialHub/auth_scopes"
    NO_AUTH_SCOPE = "__none__"

    def __init__(self, iface, parent=None, plugin_dir=None):
        super(PeruSpatialHubPanel, self).__init__(parent)
        self.iface = iface
        self.plugin_dir = plugin_dir
        self._background_tasks = set()
        self._shutting_down = False
        self._loading_layers = False
        self._filtering_tree = False
        self._health_check_running = False
        self._health_progress = 0
        self._layer_progress = (0, 0, "")
        self.auth_scopes = self.load_auth_scopes()
        self.setWindowTitle("PeruSpatial Hub")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )

        # Set main widget
        self.main_widget = QWidget()
        self.main_widget.setObjectName("peruspatialPanel")
        self.init_panel_style()
        self.setWidget(self.main_widget)
        
        # Main layout
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(12)

        # 1. Header Widget (Logo and Title)
        self.init_header()

        # Create a splitter to separate the search/tree section from the metadata/actions section
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_layout.addWidget(self.splitter)

        # Top container for search and list
        self.top_container = QWidget()
        self.top_layout = QVBoxLayout(self.top_container)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(6)

        # 2. Search & Filter Bar
        self.init_search_filters()

        # 3. Main Tree Widget (Catalog)
        self.init_tree_widget()
        
        self.top_layout.addWidget(self.search_filter_widget)
        self.top_layout.addWidget(self.tree_widget)
        self.splitter.addWidget(self.top_container)

        # Bottom container for metadata and actions
        self.bottom_container = QWidget()
        self.bottom_layout = QVBoxLayout(self.bottom_container)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_layout.setSpacing(6)

        # 4. Metadata details (QTextBrowser)
        self.init_metadata_panel()

        # 5. Action Buttons (Grid Layout)
        self.init_action_buttons()

        # 6. CRS Warning Banner
        self.init_crs_warning_banner()

        self.bottom_layout.addWidget(self.metadata_panel)
        self.bottom_layout.addWidget(self.crs_banner)
        self.bottom_layout.addWidget(self.button_grid_widget)
        self.splitter.addWidget(self.bottom_container)

        # Set default splitter sizes (give tree more space than metadata)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([440, 210])

        catalog_path = os.path.join(self.plugin_dir or os.path.dirname(__file__), "catalog", "catalog.json")
        try:
            self.catalog_data = load_catalog(catalog_path)
        except (OSError, ValueError, json.JSONDecodeError):
            self.catalog_data = {"entries": [], "sources": []}
        self.catalog_entries = self.catalog_data.get("entries", [])
        self.search_input.setToolTip(
            f"Búsqueda local en {len(self.catalog_entries):,} elementos inventariados. "
            "Escribir aquí no realiza solicitudes de red."
        )

        # Load services into Tree
        self.populate_tree()

        # Search is always local. Network access is reserved for explicit tree
        # expansion and layer loading actions.
        self._discovering_catalog = False
        self._search_cancelled = False
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.apply_catalog_search)
        self.visibilityChanged.connect(self.on_visibility_changed)
        
        # Connect signals
        self.search_input.textChanged.connect(self.schedule_filter_services)
        self.category_combo.currentIndexChanged.connect(self.schedule_filter_services)
        self.tree_widget.itemSelectionChanged.connect(self.on_selection_changed)
        self.tree_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree_widget.itemExpanded.connect(self.on_item_expanded)

        # Initial state
        self.update_buttons_state(None)

    def init_panel_style(self):
        """Keep QGIS palette and font settings, with one restrained action color."""
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        accent = "#78b9ab" if dark else "#24695f"
        foreground = "#172b26" if dark else "#ffffff"
        self.main_widget.setStyleSheet(f"""
            QWidget#peruspatialPanel QLineEdit,
            QWidget#peruspatialPanel QComboBox {{
                min-height: 26px; padding: 3px 6px;
            }}
            QWidget#peruspatialPanel QPushButton,
            QWidget#peruspatialPanel QToolButton {{
                min-height: 26px; padding: 3px 10px;
            }}
            QPushButton#addLayer:enabled {{
                background: {accent}; color: {foreground};
                border: 1px solid {accent}; border-radius: 3px;
                font-weight: bold;
            }}
            QPushButton#addLayer:hover:enabled {{ border: 1px solid palette(text); }}
            QPushButton#addLayer:pressed {{ background: palette(highlight); }}
            QPushButton#addLayer:focus {{ border: 2px solid palette(text); }}
            QTreeWidget {{ border: 1px solid palette(mid); }}
            QTreeWidget::item {{ padding: 5px 2px; }}
            QTextBrowser {{ border: 1px solid palette(mid); padding: 8px; }}
            QLabel#crsNotice {{
                border-left: 3px solid {accent}; padding: 6px 8px;
            }}
        """)

    def init_header(self):
        """Keep the logo beside the name so branding does not displace the catalog."""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(10)
        icon = QIcon(os.path.join(self.plugin_dir or os.path.dirname(__file__), "logo_solo.png"))
        if not icon.isNull():
            logo = QLabel()
            logo.setObjectName("peruspatialHeaderLogo")
            logo.setFixedSize(32, 40)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(icon.pixmap(32, 40))
            layout.addWidget(logo)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel("PeruSpatial Hub")
        title.setObjectName("peruspatialHeaderTitle")
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() + 1)
        font.setBold(True)
        title.setFont(font)
        text.addWidget(title)
        subtitle = QLabel("Datos geoespaciales del Perú")
        subtitle.setWordWrap(True)
        text.addWidget(subtitle)
        layout.addLayout(text, 1)
        self.main_layout.addWidget(header)

    def init_search_filters(self):
        """Give search its own row so narrow docks remain usable."""
        self.search_filter_widget = QWidget()
        layout = QVBoxLayout(self.search_filter_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar capas, servicios o instituciones…")
        self.search_input.setAccessibleName("Buscar en el catálogo")
        self.search_input.setClearButtonEnabled(True)
        layout.addWidget(self.search_input)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.category_combo = QComboBox()
        self.category_combo.addItem("Todas las Categorías")
        self.category_combo.addItems(CATALOG_CATEGORIES)
        self.category_combo.setAccessibleName("Filtrar por categoría")
        self.category_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.category_combo.setMinimumContentsLength(12)
        filters.addWidget(self.category_combo, 1)
        self.btn_service_status = QToolButton()
        self.btn_service_status.setText("Fuentes")
        self.btn_service_status.setToolTip("Disponibilidad y acceso a las fuentes del catálogo")
        self.btn_service_status.clicked.connect(self.show_service_status_dialog)
        filters.addWidget(self.btn_service_status)
        layout.addLayout(filters)

    def init_tree_widget(self):
        """A readable catalog with a flexible name column."""
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Catálogo / Institución", "Tipo de dato", "Fuente"])
        self.tree_widget.header().setStretchLastSection(False)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.tree_widget.setColumnWidth(1, 100)
        self.tree_widget.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.tree_widget.setColumnWidth(2, 110)
        self.tree_widget.setIndentation(14)
        self.tree_widget.setUniformRowHeights(True)
        self.tree_widget.setAlternatingRowColors(False)
        self.tree_widget.setAccessibleName("Catálogo de servicios y capas")
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)

    def init_metadata_panel(self):
        self.metadata_panel = QTextBrowser()
        self.metadata_panel.setOpenExternalLinks(True)
        self.metadata_panel.setMinimumHeight(90)
        self.metadata_panel.setAccessibleName("Detalles de la selección")
        self.metadata_panel.document().setDefaultStyleSheet(
            "h3 { font-size: medium; margin-top: 0; margin-bottom: 8px; }"
            "p { margin-top: 4px; margin-bottom: 6px; }"
        )

    def init_crs_warning_banner(self):
        self.crs_banner = QLabel()
        self.crs_banner.setObjectName("crsNotice")
        self.crs_banner.setWordWrap(True)
        self.crs_banner.setText(
            "<b>Revisar datum.</b> Esta fuente puede incluir capas en PSAD56. "
            "Compruebe el CRS de la capa y su transformación al CRS del proyecto."
        )
        self.crs_banner.setVisible(False)

    def init_action_buttons(self):
        """Expose the main action and keep utilities in a labeled menu."""
        self.button_grid_widget = QWidget()
        grid = QGridLayout(self.button_grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        self.btn_add_layer = QPushButton("Añadir al mapa")
        self.btn_add_layer.setObjectName("addLayer")
        self.btn_add_layer.clicked.connect(self.add_selected_layer)
        self.btn_register_browser = QPushButton("Registrar conexión")
        self.btn_register_browser.setToolTip("Guardar esta conexión en el navegador de QGIS")
        self.btn_register_browser.clicked.connect(self.register_selected_connection)

        self.tools_button = QToolButton()
        self.tools_button.setText("Herramientas")
        self.tools_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.tools_button)
        self.btn_copy_url = menu.addAction("Copiar URL", self.copy_selected_url)
        self.btn_open_browser = menu.addAction("Abrir en navegador", self.open_selected_web)
        self.btn_service_access = menu.addAction("Configurar acceso privado", self.configure_selected_service_access)
        menu.addSeparator()
        self.btn_register_all = menu.addAction("Registrar todas las conexiones", self.register_all_connections)
        self.btn_health_check = menu.addAction("Verificar servidores", self.check_all_servers_health)
        menu.addSeparator()
        self.btn_about = menu.addAction("Acerca de PeruSpatial Hub", self.show_about_dialog)
        self.tools_button.setMenu(menu)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Cargando…")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setVisible(False)
        grid.addWidget(self.btn_add_layer, 0, 0, 1, 2)
        grid.addWidget(self.btn_register_browser, 1, 0)
        grid.addWidget(self.tools_button, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.addWidget(self.progress_bar, 2, 0, 1, 2)

    def _ui_available(self):
        return not self._shutting_down and not sip.isdeleted(self)

    def _update_progress(self):
        if not self._ui_available():
            return
        if self._loading_layers:
            value, total, text = self._layer_progress
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(value)
            self.progress_bar.setFormat(text)
            self.progress_bar.setVisible(True)
        elif self._health_check_running:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(self._health_progress)
            self.progress_bar.setFormat("Verificando servidores en segundo plano… %p%")
            self.progress_bar.setVisible(True)
        else:
            self.progress_bar.setVisible(False)

    def _on_health_progress(self, value):
        self._health_progress = int(value)
        self._update_progress()

    def show_about_dialog(self):
        """Opens the About dialog with developer information and links."""
        dialog = AboutDialog(self, self.plugin_dir)
        dialog.exec()

    def show_service_status_dialog(self):
        """Shows the research status of unavailable or restricted services."""
        dialog = ServiceStatusDialog(self, self.catalog_data)
        dialog.exec()

    # ------------------------------------------------------------------
    #  Context menu
    # ------------------------------------------------------------------

    CONTAINER_TYPES = {"server", "folder", "arcgis_service", "arcgis_group", "ogc_service", "wms_group"}
    LAYER_TYPES = {"arcgis_map_layer", "arcgis_vector_layer", "arcgis_raster_layer", "wms_layer"}

    @staticmethod
    def is_map_service(data):
        return data.get("type") == "arcgis_service" and (
            data.get("service_kind") == "MapServer" or data.get("stype") == "arcgis_mapserver")

    def can_add_layer(self, data):
        return data.get("type") in self.LAYER_TYPES or self.is_map_service(data)

    @staticmethod
    def entry_source_type(data):
        if not data:
            return ""
        if data.get("service_kind") in {"MapServer", "FeatureServer", "ImageServer"}:
            return data["service_kind"]
        if data.get("stype") == "wms" or data.get("type") == "wms_layer":
            return "WMS"
        try:
            components = urllib.parse.urlsplit(data.get("service_url") or data.get("url", "")).path.split("/")
        except ValueError:
            components = []
        for component in components:
            if component in {"MapServer", "FeatureServer", "ImageServer"}:
                return component
        return {"arcgis_rest": "REST", "arcgis_mapserver": "MapServer",
                "arcgisfeatureserver": "FeatureServer", "arcgis_imageserver": "ImageServer"}.get(data.get("stype"), "")

    def set_item_metadata(self, item, data):
        item.setData(0, Qt.ItemDataRole.UserRole, data)
        source = self.entry_source_type(data)
        item.setText(2, source)
        item.setToolTip(2, f"{source} · ArcGIS REST" if source in {"MapServer", "FeatureServer", "ImageServer"} else source)

    def entry_display_type(self, data):
        if self.is_map_service(data):
            return "Ráster"
        if data.get("type") == "wms_layer":
            return "Ráster"
        if data.get("service_kind") == "ImageServer":
            return "Ráster"
        kind = data.get("data_kind")
        if kind in {"vectorial", "raster", "tabla"}:
            label = {"vectorial": "Vectorial", "raster": "Ráster", "tabla": "Tabla"}[kind]
            return label
        return self.friendly_type(data.get("stype", data.get("type", "")))

    def show_context_menu(self, position):
        """Show a right-click context menu with actions appropriate for the selected node."""
        item = self.tree_widget.itemAt(position)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return

        if not item.isSelected():
            self.tree_widget.clearSelection()
            self.tree_widget.setCurrentItem(item)
            item.setSelected(True)
        single_selection = len(self.tree_widget.selectedItems()) == 1
        menu = QMenu(self)
        ntype = data.get("type", "")

        if ntype in self.CONTAINER_TYPES:
            if self.is_map_service(data):
                menu.addAction("Añadir mapa ráster", self.add_selected_layer).setEnabled(not self._loading_layers)
            menu.addAction("Expandir / contraer", lambda: item.setExpanded(not item.isExpanded()))
            if data.get("is_loaded", False):
                menu.addAction("Actualizar contenido", lambda: self.refresh_node(item))
            menu.addSeparator()
            if ntype != "arcgis_group":
                menu.addAction("Registrar conexión", self.register_selected_connection).setEnabled(single_selection)
            menu.addAction("Copiar URL", self.copy_selected_url).setEnabled(single_selection)
            menu.addAction("Abrir en navegador", self.open_selected_web).setEnabled(single_selection)
        elif ntype in self.LAYER_TYPES:
            selected = self.tree_widget.selectedItems()
            if len(selected) > 1:
                layer_count = sum(
                    1 for it in selected
                    if self.can_add_layer(it.data(0, Qt.ItemDataRole.UserRole) or {})
                )
                menu.addAction(f"Añadir {layer_count} capas al Mapa", self.add_selected_layer).setEnabled(
                    layer_count > 0 and not self._loading_layers)
            else:
                menu.addAction("Añadir al mapa", self.add_selected_layer).setEnabled(not self._loading_layers)
                if ntype == "arcgis_map_layer" and not data.get("is_table"):
                    menu.addAction("Añadir como mapa ráster", lambda: self.add_selected_layer(as_raster=True)).setEnabled(not self._loading_layers)
            menu.addSeparator()
            menu.addAction("Copiar URL", self.copy_selected_url).setEnabled(single_selection)
            menu.addAction("Abrir en navegador", self.open_selected_web).setEnabled(single_selection)
            menu.addSeparator()
            if self._is_favorite(data):
                menu.addAction("Quitar de favoritos", lambda: self.remove_from_favorites(item))
            else:
                menu.addAction("Añadir a favoritos", lambda: self.add_to_favorites(item))

        if self.normalize_auth_scope(data.get("service_url") or data.get("url", "")):
            menu.addSeparator()
            menu.addAction("Configurar acceso privado", self.configure_selected_service_access).setEnabled(single_selection)

        if menu.actions():
            menu.exec(self.tree_widget.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    #  Refresh node
    # ------------------------------------------------------------------

    def refresh_node(self, item):
        """Force a reload of a previously loaded server, folder or service node."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        data["is_loaded"] = False
        data["is_loading"] = False
        data["_request_generation"] = data.get("_request_generation", 0) + 1
        self.set_item_metadata(item, data)
        item.takeChildren()
        dummy = QTreeWidgetItem(item)
        dummy.setText(0, "Recargando...")
        if item.isExpanded():
            self.load_dynamic_node(item)
        else:
            item.setExpanded(True)

    # ------------------------------------------------------------------
    #  Favorites
    # ------------------------------------------------------------------

    FAVORITES_SETTINGS_KEY = "PeruSpatialHub/favorites"

    def _favorite_key(self, data):
        """Return a stable identifier for a favorite entry."""
        return favorite_identity(data)

    def _is_favorite(self, data):
        """Check whether a node is already bookmarked."""
        key = self._favorite_key(data)
        return any(self._favorite_key(f) == key for f in self.load_favorites())

    def load_favorites(self):
        """Load favorites list from QGIS Settings."""
        raw = QgsSettings().value(self.FAVORITES_SETTINGS_KEY, "")
        if not raw:
            return []
        try:
            favorites = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return [entry for entry in favorites if isinstance(entry, dict)
                and all(isinstance(entry.get(key), str) and entry[key]
                        for key in ("url", "name"))] if isinstance(favorites, list) else []

    def save_favorites(self, favorites):
        """Persist favorites list to QGIS Settings."""
        settings = QgsSettings()
        if favorites:
            settings.setValue(
                self.FAVORITES_SETTINGS_KEY,
                json.dumps(favorites, ensure_ascii=False),
            )
        else:
            settings.remove(self.FAVORITES_SETTINGS_KEY)

    def add_to_favorites(self, item):
        """Bookmark the selected layer for quick access."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        # Store only the essential fields, no internal keys
        storable = {
            k: v for k, v in data.items()
            if not k.startswith("_") and k not in {"is_loaded", "is_loading"}
        }
        favorites = self.load_favorites()
        key = self._favorite_key(storable)
        if any(self._favorite_key(f) == key for f in favorites):
            return  # already bookmarked
        favorites.append(storable)
        self.save_favorites(favorites)
        self.populate_favorites_tree()
        self.iface.messageBar().pushMessage(
            "PeruSpatial Hub",
            f"'{storable.get('name', '')}' añadido a Favoritos.",
            level=3, duration=2,
        )

    def remove_from_favorites(self, item):
        """Remove the selected entry from bookmarks."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        key = self._favorite_key(data)
        favorites = [f for f in self.load_favorites() if self._favorite_key(f) != key]
        self.save_favorites(favorites)
        self.populate_favorites_tree()
        self.iface.messageBar().pushMessage(
            "PeruSpatial Hub",
            f"'{data.get('name', '')}' eliminado de Favoritos.",
            level=3, duration=2,
        )

    def populate_favorites_tree(self):
        """Rebuild the favorites branch from persisted bookmarks."""
        if not hasattr(self, "favorites_root"):
            return
        self.favorites_root.takeChildren()
        favorites = self.load_favorites()
        if not favorites:
            placeholder = QTreeWidgetItem(self.favorites_root)
            placeholder.setText(0, "Sin favoritos. Use el menú contextual de una capa.")
            placeholder.setForeground(0, QColor("#888"))
            return
        for fav in favorites:
            fav_item = QTreeWidgetItem(self.favorites_root)
            inst = fav.get("institution", "")
            fav_item.setText(0, f"{inst} — {fav.get('name', 'Sin nombre')}" if inst else fav.get("name", "Sin nombre"))
            fav_item.setText(1, self.entry_display_type(fav))
            fav_item.setToolTip(0, fav.get("url", ""))
            self.set_item_metadata(fav_item, fav)
            # If it is a container type, allow live expansion
            if fav.get("type") in self.CONTAINER_TYPES:
                fav["is_loaded"] = False
                self.set_item_metadata(fav_item, fav)
                dummy = QTreeWidgetItem(fav_item)
                dummy.setText(0, "Expandir para consultar en vivo...")

    # ------------------------------------------------------------------
    #  Health check
    # ------------------------------------------------------------------

    def check_all_servers_health(self):
        """Test every live server without blocking QGIS' interface thread."""
        if not self._ui_available() or self._health_check_running:
            return
        self._health_check_running = True
        self._health_progress = 0
        self._update_progress()
        self.btn_health_check.setEnabled(False)
        servers = [dict(server) for server in self.live_servers]
        auth_configs = {
            server["url"]: self.auth_config_for_url(server["url"])
            for server in servers
        }

        def worker(task):
            results = []
            total = max(1, len(servers))
            for idx, server in enumerate(servers):
                if task.isCanceled():
                    return None
                try:
                    if server["stype"] == "arcgis_rest":
                        metadata = self.fetch_arcgis_json(
                            server["url"],
                            timeout=8,
                            attempts=1,
                            authcfg=auth_configs[server["url"]],
                        )
                        arcgis_directory(metadata)
                    else:
                        payload = self.read_service_https(
                            _wms_capabilities_url(server["url"]),
                            timeout=8,
                            headers={
                                "User-Agent": PLUGIN_USER_AGENT,
                                "Accept": "application/xml,text/xml",
                            },
                            authcfg=auth_configs[server["url"]],
                        )
                        self.parse_wms_layer_catalog(payload)
                    results.append((server, True, ""))
                except Exception as exc:
                    results.append((server, False, str(exc)))
                task.setProgress(((idx + 1) / total) * 100)
            return results

        task_holder = {}

        def finished(exception, results=None):
            task = task_holder.get("task")
            if task is not None:
                self._background_tasks.discard(task)
            if self._shutting_down:
                return
            self._health_check_running = False
            self._update_progress()
            self.btn_health_check.setEnabled(True)
            if exception is not None:
                QMessageBox.warning(self, "Error de verificación", str(exception))
                return
            if results is None:
                return
            self.show_health_results(results)

        task = QgsTask.fromFunction(
            "PeruSpatial Hub: verificar servidores",
            worker,
            on_finished=finished,
        )
        task_holder["task"] = task
        task.progressChanged.connect(self._on_health_progress)
        self._background_tasks.add(task)
        QgsApplication.taskManager().addTask(task)

    def show_health_results(self, results):
        """Display server health results after the background task finishes."""

        online = sum(1 for _, ok, _ in results if ok)
        offline = len(results) - online

        html_rows = []
        for server, ok, error in results:
            icon = "En línea" if ok else "Sin respuesta"
            name = escape(f"{server['institution']} — {server['name']}")
            detail = "" if ok else f"<br><small>{escape(str(error)[:200])}</small>"
            html_rows.append(f"<tr><td valign='top'>{icon}</td><td>{name}{detail}</td></tr>")

        dialog = QDialog(self)
        dialog.setWindowTitle("Estado de servidores")
        dialog.setMinimumSize(560, 400)
        layout = QVBoxLayout(dialog)

        summary = QLabel(
            f"<h3>Verificación completada</h3>"
            f"<p>{online} en línea · {offline} sin respuesta</p>"
        )
        layout.addWidget(summary)

        browser = QTextBrowser()
        browser.setHtml(f"<table cellspacing='0' cellpadding='8'><tr><th align='left'>Estado</th><th align='left'>Servicio</th></tr>{''.join(html_rows)}</table>")
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    @classmethod
    def normalize_auth_scope(cls, url):
        """Return a stable HTTPS service scope without query strings or fragments."""
        parts = urllib.parse.urlsplit(str(url or "").strip())
        if parts.scheme.casefold() != "https" or not parts.hostname:
            return ""
        host = parts.hostname.casefold()
        try:
            port = parts.port
        except ValueError:
            return ""
        if port and port != 443:
            host = f"{host}:{port}"
        path = "/" + "/".join(part for part in parts.path.split("/") if part)
        return urllib.parse.urlunsplit(("https", host, path.rstrip("/") or "/", "", ""))

    @classmethod
    def load_auth_scopes(cls):
        raw = QgsSettings().value(cls.AUTH_SCOPES_SETTINGS_KEY, "")
        if not raw:
            return {}
        try:
            scopes = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(scopes, dict):
            return {}
        return {
            cls.normalize_auth_scope(scope): str(authcfg).strip()
            for scope, authcfg in scopes.items()
            if cls.normalize_auth_scope(scope) and isinstance(authcfg, str) and authcfg.strip()
        }

    def save_auth_scopes(self):
        settings = QgsSettings()
        if self.auth_scopes:
            settings.setValue(
                self.AUTH_SCOPES_SETTINGS_KEY,
                json.dumps(self.auth_scopes, ensure_ascii=False, sort_keys=True),
            )
        else:
            settings.remove(self.AUTH_SCOPES_SETTINGS_KEY)

    def auth_scope_for_url(self, url):
        """Return the most specific configuration or explicit anonymous marker."""
        target = urllib.parse.urlsplit(self.normalize_auth_scope(url))
        if not target.hostname:
            return ""
        matches = []
        for scope, authcfg in self.auth_scopes.items():
            candidate = urllib.parse.urlsplit(scope)
            if (candidate.scheme, candidate.netloc) != (target.scheme, target.netloc):
                continue
            candidate_path = candidate.path.rstrip("/") or "/"
            target_path = target.path.rstrip("/") or "/"
            path_matches = (
                candidate_path == "/"
                or target_path == candidate_path
                or target_path.startswith(candidate_path + "/")
            )
            if path_matches:
                matches.append((len(candidate_path), authcfg))
        return max(matches, default=(0, ""))[1]

    def auth_config_for_url(self, url):
        matched_authcfg = self.auth_scope_for_url(url)
        return "" if matched_authcfg == self.NO_AUTH_SCOPE else matched_authcfg

    @staticmethod
    def auth_provider_key(service):
        stype = (service or {}).get("stype", "")
        if stype == "wms":
            return "wms"
        if stype in ("arcgisfeatureserver", "arcgis_vector_layer"):
            return "arcgisfeatureserver"
        return "arcgismapserver"

    def configure_selected_service_access(self):
        selected_items = self.tree_widget.selectedItems()
        if len(selected_items) != 1:
            return
        service = selected_items[0].data(0, Qt.ItemDataRole.UserRole) or {}
        service_url = service.get("service_url") or service.get("url")
        scope = self.normalize_auth_scope(service_url)
        if not scope:
            QMessageBox.warning(
                self,
                "Acceso no disponible",
                "El elemento seleccionado no tiene un servicio HTTPS válido.",
            )
            return

        current_authcfg = self.auth_config_for_url(service_url)
        dialog = ServiceAccessDialog(
            service.get("name") or service.get("institution") or "Servicio",
            scope,
            current_authcfg,
            self.auth_provider_key(service),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        authcfg = dialog.config_id()
        if authcfg:
            self.auth_scopes[scope] = authcfg
            message = (
                "El acceso quedó vinculado a este servicio en el perfil local de QGIS. "
                "Las credenciales permanecen cifradas en esta PC."
            )
        else:
            # Keep an explicit anonymous override at this scope. This matters when
            # a broader parent directory uses authentication but one child does not.
            self.auth_scopes[scope] = self.NO_AUTH_SCOPE
            message = "Este servicio volverá a utilizarse sin autenticación."
        self.save_auth_scopes()
        # Rebuild lazy nodes so an authenticated directory can reveal content
        # which was not visible to the previous anonymous request.
        self.populate_tree()
        self.update_buttons_state(None)
        self.apply_catalog_search()
        self.iface.reloadConnections()
        QMessageBox.information(self, "Acceso actualizado", message)

    def read_service_https(self, url, timeout=15, headers=None, authcfg=""):
        """Read HTTPS through QGIS, applying proxy, TLS and auth configuration."""
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.casefold() != "https" or not parts.hostname:
            raise ValueError("solo se permiten servicios HTTPS con un host válido")

        request = QNetworkRequest(QUrl(url))
        prepare_request(request)
        for name, value in (headers or {}).items():
            request.setRawHeader(str(name).encode("ascii"), str(value).encode("utf-8"))
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(max(1, int(timeout * 1000)))

        reply = QgsNetworkAccessManager.blockingGet(request, authcfg or "", True)
        if reply.error() != QNetworkReply.NetworkError.NoError:
            raise RuntimeError(reply.errorString() or "error de red sin descripción")

        status_value = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status = int(status_value) if status_value is not None else 0
        if status and (status < 200 or status >= 300):
            raise RuntimeError(f"HTTP {status}")
        payload = bytes(reply.content())
        if len(payload) > MAX_HTTP_RESPONSE_BYTES:
            raise RuntimeError("la respuesta del servidor excede el límite permitido")
        return payload

    def fetch_arcgis_json(self, url, timeout=15, attempts=2, authcfg=None):
        """Read ArcGIS REST metadata with one retry for intermittent public servers."""
        request_url = _url_with_json(url)
        request_authcfg = self.auth_config_for_url(url) if authcfg is None else authcfg
        last_error = None
        for attempt in range(attempts):
            try:
                payload = self.read_service_https(
                    request_url,
                    timeout=timeout,
                    headers={
                        "User-Agent": PLUGIN_USER_AGENT,
                        "Accept": "application/json",
                    },
                    authcfg=request_authcfg,
                )
                data = json.loads(payload.decode("utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError("el servidor no devolvió un objeto JSON")
                if data.get("error"):
                    error = data["error"]
                    details = "; ".join(error.get("details") or [])
                    message = error.get("message") or "error REST sin descripción"
                    raise RuntimeError(f"ArcGIS REST {error.get('code', '')}: {message}. {details}".strip())
                return data
            except (
                OSError,
                ValueError,
                RuntimeError,
                json.JSONDecodeError,
            ) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(0.35)
        raise RuntimeError(f"No se pudo consultar {request_url}: {last_error}")

    @staticmethod
    def service_kind_from_url(url, stype=None):
        if stype in ARCGIS_SERVICE_TYPES:
            return ARCGIS_SERVICE_TYPES[stype]
        path = urllib.parse.urlsplit(url).path.rstrip("/")
        ending = path.split("/")[-1]
        if ending in ("MapServer", "FeatureServer", "ImageServer"):
            return ending
        return None


    def section_font(self):
        font = QFont(self.font())
        font.setBold(True)
        return font

    def populate_tree(self):
        """Fills the TreeWidget grouping services by institution and adding live servers."""
        self.tree_widget.clear()

        self.search_results_root = QTreeWidgetItem(self.tree_widget)
        self.search_results_root.setText(0, "Resultados de búsqueda")
        self.search_results_root.setText(1, "Local")
        self.search_results_root.setFont(0, self.section_font())
        self.set_item_metadata(self.search_results_root, None)
        self.search_results_root.setHidden(True)
        
        # The old fixed layer URLs contained many retired services. Start from
        # live repository roots and discover their current services/layers.
        explorer_root = QTreeWidgetItem(self.tree_widget)
        explorer_root.setText(0, "Servidores disponibles")
        explorer_root.setFont(0, self.section_font())
        self.set_item_metadata(explorer_root, None)


        self.live_servers = [
            s for s in LIVE_SERVERS
            if (
                s["stype"] == "arcgis_rest"
                and _clean_rest_url(s["url"]) in ACTIVE_REST_ROOTS
            ) or (
                s["stype"] == "wms"
                and _clean_rest_url(s["url"]) in ACTIVE_WMS_ROOTS
            )
        ]
        for s in self.live_servers:
            server_item = QTreeWidgetItem(explorer_root)
            server_item.setText(0, f"{s['institution']} - {s['name']}")
            is_arcgis = s["stype"] == "arcgis_rest"
            server_item.setText(1, "Institución" if is_arcgis else "Servicio")
            self.set_item_metadata(server_item, {
                "type": "server" if is_arcgis else "ogc_service",
                "stype": s["stype"],
                "url": s["url"],
                "name": s["name"],
                "institution": s["institution"],
                "category": s["category"],
                "crs_warning": s.get("crs_warning", False),
                "is_loaded": False
            })
            # Add a dummy child so both REST and WMS catalogs can be expanded.
            dummy = QTreeWidgetItem(server_item)
            dummy.setText(0, "Expandir para explorar...")

        # Favorites section
        self.favorites_root = QTreeWidgetItem(self.tree_widget)
        self.favorites_root.setText(0, "Favoritos")
        self.favorites_root.setFont(0, self.section_font())
        self.set_item_metadata(self.favorites_root, None)
        self.populate_favorites_tree()

        # Show institutions immediately; remote folders remain closed and are
        # loaded only when the user explicitly expands one of them.
        self.tree_widget.collapseAll()
        explorer_root.setExpanded(True)
        if self.favorites_root.childCount():
            self.favorites_root.setExpanded(True)

    def friendly_type(self, type_str):
        """Translates technical connection type to friendly name."""
        mapping = {
            "arcgis_mapserver": "Ráster",
            "arcgisfeatureserver": "Vectorial",
            "arcgis_imageserver": "Ráster",
            "arcgis_map_layer": "Por consultar",
            "arcgis_vector_layer": "Vectorial",
            "arcgis_raster_layer": "Ráster",
            "wms": "Servicio",
        }
        return mapping.get(type_str, type_str)

    @staticmethod
    def normalize_search_text(value):
        """Normalize case and accents so geologia also matches Geología."""
        return _normalize_catalog_text(value)

    def item_matches_search(self, item, search_text, selected_category):
        """Match only the visible node name, never metadata or technical fields."""
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        category = data.get("category")
        category_matches = (
            selected_category == "Todas las Categorías"
            or category is None
            or category == selected_category
        )
        if not category_matches:
            return False
        if not search_text:
            return True

        if data.get("_catalog_result"):
            return True

        return search_text in self.normalize_search_text(item.text(0))

    def filter_tree_item(self, item, search_text, selected_category):
        """Filter a complete branch and retain ancestors of matching layers."""
        if item is getattr(self, "search_results_root", None):
            for index in range(item.childCount()):
                self.filter_tree_item(item.child(index), search_text, selected_category)
            visible = bool(search_text)
            item.setHidden(not visible)
            return visible

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None and item.parent() is not None and not item.childCount():
            # Loading/error/expand hints belong to their parent; they are not
            # independent search matches and must not bypass category filters.
            item.setHidden(False)
            return False
        own_match = self.item_matches_search(item, search_text, selected_category)
        descendant_match = False

        for index in range(item.childCount()):
            child = item.child(index)
            if self.filter_tree_item(child, search_text, selected_category):
                descendant_match = True

        visible = own_match or descendant_match
        item.setHidden(not visible)

        if search_text and descendant_match:
            item.setExpanded(True)
        return visible

    def filter_services(self):
        """Filter every tree level, including folders, groups and REST layers."""
        search_text = self.normalize_search_text(self.search_input.text().strip())
        selected_category = self.category_combo.currentText()

        self._filtering_tree = True
        try:
            for i in range(self.tree_widget.topLevelItemCount()):
                self.filter_tree_item(
                    self.tree_widget.topLevelItem(i), search_text, selected_category
                )
        finally:
            self._filtering_tree = False

    def populate_catalog_results(self, search_text, selected_category):
        """Rebuild the lightweight result branch from the bundled inventory."""
        self.search_results_root.takeChildren()
        if not search_text:
            self.search_results_root.setHidden(True)
            return

        results, total = search_catalog(
            self.catalog_entries,
            search_text,
            selected_category,
            limit=200,
        )
        self.search_results_root.setText(
            0, f"Resultados: {len(results)} de {total}"
        )
        self.search_results_root.setHidden(False)
        if not results:
            empty = QTreeWidgetItem(self.search_results_root)
            empty.setText(0, "Sin coincidencias. Pruebe otro término o categoría.")
            empty.setToolTip(0, empty.text(0))
            empty.setFlags(Qt.ItemFlag.ItemIsEnabled)

        for entry in results:
            data = {
                key: value
                for key, value in entry.items()
                if key not in {"display_type", "path", "search_text", "_search_text"}
            }
            data["_catalog_result"] = True
            if data.get("stale"):
                data["description"] = (data.get("description", "") +
                    " Inventario anterior: no se pudo volver a verificar esta entrada. " +
                    f"Última referencia: {data.get('last_verified_at') or 'sin fecha'}.")
            item = QTreeWidgetItem(self.search_results_root)
            institution = data.get("institution", "")
            item.setText(0, f"{institution} — {data.get('name', 'Sin nombre')}")
            item.setText(
                1,
                self.entry_display_type(data)
                + (" · Sin verificar" if data.get("stale") else ""),
            )
            item.setToolTip(0, entry.get("path", data.get("url", "")))
            self.set_item_metadata(item, data)

            if data.get("type") in {"server", "folder", "arcgis_service", "ogc_service"}:
                data["is_loaded"] = False
                self.set_item_metadata(item, data)
                dummy = QTreeWidgetItem(item)
                dummy.setText(0, "Expandir para consultar en vivo...")

        self.search_results_root.setExpanded(True)

    def apply_catalog_search(self):
        """Apply a fully local search; this method never performs network I/O."""
        if self._shutting_down or sip.isdeleted(self) or not hasattr(self, "search_results_root"):
            return
        search_text = self.normalize_search_text(self.search_input.text().strip())
        selected_category = self.category_combo.currentText()
        self.tree_widget.setUpdatesEnabled(False)
        try:
            self.populate_catalog_results(search_text, selected_category)
            self.filter_services()
        finally:
            self.tree_widget.setUpdatesEnabled(True)

    def schedule_filter_services(self, *_args):
        """Debounce local filtering without contacting external services."""
        self.search_timer.stop()
        if self.isVisible():
            self._search_cancelled = False
            self.search_timer.start()

    def cancel_pending_search(self):
        """Stop deferred UI filtering and cancel explicit loading work."""
        self._search_cancelled = True
        self.search_timer.stop()

    def on_visibility_changed(self, visible):
        """Pause local filtering and explicit loading while the panel is hidden."""
        if visible:
            self._search_cancelled = False
            self.search_timer.start()
        else:
            self.cancel_pending_search()

    def closeEvent(self, event):
        self.cancel_pending_search()
        super().closeEvent(event)

    def hideEvent(self, event):
        self.cancel_pending_search()
        super().hideEvent(event)

    def on_selection_changed(self):
        """Loads metadata details when a service node is selected."""
        if self._shutting_down or sip.isdeleted(self):
            return
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            self.update_buttons_state(None)
            return

        item = selected_items[0]
        s = item.data(0, Qt.ItemDataRole.UserRole)
        
        self.update_buttons_state(s)

    def on_item_expanded(self, item):
        """Called when a tree node is expanded. Loads subfolders/services dynamically."""
        if self._filtering_tree or self._shutting_down:
            return
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        if (
            node_data
            and node_data.get("type") in ["server", "folder", "arcgis_service", "ogc_service"]
            and not node_data.get("is_loaded", False)
            and not node_data.get("is_loading", False)
        ):
            self.load_dynamic_node(item)

    def load_dynamic_node(self, item):
        """Fetch a remote catalog in a QGIS task, then update the tree on the GUI thread."""
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        url = node_data["url"]
        stype = node_data["stype"]
        authcfg = self.auth_config_for_url(url)
        discovering_catalog = self._discovering_catalog
        request_generation = node_data.get("_request_generation", 0) + 1
        node_data["_request_generation"] = request_generation
        node_data["is_loading"] = True
        self.set_item_metadata(item, node_data)
        item.takeChildren()
        loading_node = QTreeWidgetItem(item)
        loading_node.setText(0, "Cargando...")
        if self._search_cancelled or not self.isVisible():
            if loading_node.parent() is item:
                item.removeChild(loading_node)
            node_data["is_loading"] = False
            self.set_item_metadata(item, node_data)
            return

        def worker(task):
            if task.isCanceled():
                return None
            if stype == "arcgis_rest":
                data = self.fetch_arcgis_json(
                    url,
                    timeout=6 if discovering_catalog else 15,
                    attempts=1 if discovering_catalog else 2,
                    authcfg=authcfg,
                )
                return "arcgis_directory", data
            if node_data.get("type") == "arcgis_service":
                data = self.fetch_arcgis_json(
                    url,
                    timeout=6 if discovering_catalog else 15,
                    attempts=1 if discovering_catalog else 2,
                    authcfg=authcfg,
                )
                kind = node_data.get("service_kind") or self.service_kind_from_url(url, stype)
                data = resolve_arcgis_inventory(data, kind,
                    lambda part: self.fetch_arcgis_json(_append_rest_path(url, part), timeout=15, attempts=1, authcfg=authcfg),
                    cancelled=task.isCanceled)
                return "arcgis_service", data
            if stype == "wms":
                payload = self.read_service_https(
                    _wms_capabilities_url(url),
                    timeout=30,
                    headers={
                        "User-Agent": PLUGIN_USER_AGENT,
                        "Accept": "application/xml,text/xml",
                    },
                    authcfg=authcfg,
                )
                return "wms", payload
            raise RuntimeError(f"Tipo REST no compatible: {stype}")

        task_holder = {}

        def finished(exception, result=None):
            task = task_holder.get("task")
            if task is not None:
                self._background_tasks.discard(task)
            if self._shutting_down:
                return
            try:
                if item.treeWidget() is not self.tree_widget:
                    return
                current_data = item.data(0, Qt.ItemDataRole.UserRole) or {}
                if current_data.get("_request_generation") != request_generation:
                    return
            except RuntimeError:
                return

            loaded_ok = False
            try:
                item.takeChildren()
                if exception is not None:
                    raise exception
                if result is None:
                    raise RuntimeError("carga cancelada")

                result_kind, payload = result
                if result_kind == "arcgis_directory":
                    folders, directory_services = arcgis_directory(payload)
                    inst = node_data["institution"]
                    cat = node_data["category"]

                    # Folders
                    for f in folders:
                        folder_name = f
                        furl = _append_rest_path(url, folder_name)

                        f_item = QTreeWidgetItem(item)
                        f_item.setText(0, folder_name)
                        f_item.setText(1, "Carpeta")
                        f_item.setFont(0, self.section_font())
                        self.set_item_metadata(f_item, {
                            "type": "folder",
                            "stype": "arcgis_rest",
                            "url": furl,
                            "is_loaded": False,
                            "name": folder_name,
                            "institution": inst,
                            "category": cat,
                            "crs_warning": node_data.get("crs_warning", False),
                        })
                        dummy = QTreeWidgetItem(f_item)
                        dummy.setText(0, "Expandir para explorar...")

                    # Services
                    for s in directory_services:
                        sname = s.get("name")
                        stype_str = s.get("type")
                        if not sname or stype_str not in (
                            "MapServer", "FeatureServer", "ImageServer"
                        ):
                            continue

                        friendly_type = None
                        if stype_str == "MapServer":
                            friendly_type = "arcgis_mapserver"
                        elif stype_str == "FeatureServer":
                            friendly_type = "arcgisfeatureserver"
                        elif stype_str == "ImageServer":
                            friendly_type = "arcgis_imageserver"

                        sname_short = sname.split('/')[-1]
                        surl = _service_url(url, sname, stype_str)
                        is_image = stype_str == "ImageServer"

                        s_item = QTreeWidgetItem(item)
                        s_item.setText(0, sname_short)
                        s_item.setText(1, self.friendly_type(friendly_type))
                        self.set_item_metadata(s_item, {
                            "type": "arcgis_raster_layer" if is_image else "arcgis_service",
                            "stype": friendly_type,
                            "service_kind": stype_str,
                            "url": surl,
                            "name": sname_short,
                            "institution": inst,
                            "category": cat,
                            "description": f"Servicio REST {stype_str} en vivo provisto por {inst}.",
                            "crs_warning": node_data.get("crs_warning", False),
                            "is_loaded": is_image,
                        })
                        if not is_image:
                            dummy = QTreeWidgetItem(s_item)
                            dummy.setText(0, "Expandir para ver capas REST...")

                elif result_kind == "arcgis_service":
                    self.populate_arcgis_service_layers(item, node_data, payload)
                else:
                    self.populate_wms_layers(item, node_data, payload)
                loaded_ok = True
            except Exception as exc:
                error_node = QTreeWidgetItem(item)
                error_node.setText(0, f"Error al cargar: {str(exc)}")
                error_node.setText(1, "Reintentar al expandir")
                error_node.setForeground(0, QColor("red"))
            finally:
                node_data["is_loaded"] = loaded_ok
                node_data["is_loading"] = False
                self.set_item_metadata(item, node_data)
                if self.search_input.text().strip() and not self._discovering_catalog:
                    self.filter_services()

        task = QgsTask.fromFunction(
            f"PeruSpatial Hub: cargar {node_data.get('name', 'servicio')}",
            worker,
            on_finished=finished,
        )
        task_holder["task"] = task
        self._background_tasks.add(task)
        QgsApplication.taskManager().addTask(task)

    def cancel_background_tasks(self):
        """Prevent callbacks from touching the panel while the plugin is unloading."""
        self._shutting_down = True
        if not sip.isdeleted(self):
            self.cancel_pending_search()
        for task in tuple(self._background_tasks):
            task.cancel()
        self._background_tasks.clear()

    @staticmethod
    def parse_wms_layer_catalog(payload):
        return parse_wms_layer_catalog(payload)

    def populate_wms_layers(self, service_item, service_data, payload):
        """Populate a WMS catalog with importable named layers from GetCapabilities."""
        root_layer = self.parse_wms_layer_catalog(payload)

        service_url = _wms_service_url(service_data["url"])
        institution = service_data["institution"]
        category = service_data["category"]
        created_layers = 0

        def add_layer_node(layer_data, parent_item, inherited_crs):
            nonlocal created_layers
            title = layer_data["title"] or "Grupo WMS"
            layer_name = layer_data["name"]
            own_crs = layer_data["crs"]
            available_crs = merge_crs(inherited_crs, own_crs)
            children = layer_data["children"]

            if layer_name:
                tree_item = QTreeWidgetItem(parent_item)
                tree_item.setText(0, title)
                tree_item.setText(1, "Ráster")
                self.set_item_metadata(tree_item, {
                    "type": "wms_layer",
                    "stype": "wms",
                    "url": service_data["url"],
                    "service_url": service_url,
                    "layer_name": layer_name,
                    "name": title,
                    "institution": institution,
                    "category": category,
                    "crs_options": available_crs,
                    "description": f"Capa WMS en vivo publicada por {institution}.",
                    "is_loaded": True,
                })
                parent_for_children = tree_item
                created_layers += 1
            else:
                parent_for_children = parent_item
                if children and parent_item is not service_item:
                    group_item = QTreeWidgetItem(parent_item)
                    group_item.setText(0, title)
                    group_item.setText(1, "Grupo")
                    group_item.setFont(0, self.section_font())
                    self.set_item_metadata(group_item, {
                        "type": "wms_group",
                        "stype": "wms",
                        "url": service_data["url"],
                        "name": title,
                        "institution": institution,
                        "category": category,
                        "is_loaded": True,
                    })
                    parent_for_children = group_item

            for child_layer_data in children:
                add_layer_node(child_layer_data, parent_for_children, available_crs)

        add_layer_node(root_layer, service_item, [])
        if not created_layers:
            raise RuntimeError("El servidor WMS respondió, pero no publicó capas con nombre")

    def populate_arcgis_service_layers(self, service_item, service_data, metadata):
        """Create importable leaf nodes for a MapServer or FeatureServer."""
        service_url = _clean_rest_url(service_data["url"])
        service_reference = metadata.get("spatialReference") or (metadata.get("fullExtent") or {}).get("spatialReference")
        service_data["crs_warning"] = bool(service_data.get("crs_warning")) or is_psad56_reference(service_reference)
        if metadata.get("_inventory_errors"):
            service_data["metadata_warnings"] = sorted(set(service_data.get("metadata_warnings", []) + ["incomplete_sublayers"]))
        service_kind = service_data.get("service_kind") or self.service_kind_from_url(
            service_url, service_data.get("stype")
        )
        entries = arcgis_service_records(metadata, service_kind)

        if not entries:
            raise RuntimeError("el servicio REST no publicó capas ni tablas importables")

        by_id = {entry.get("id"): entry for entry in entries if entry.get("id") is not None}
        created = {}

        def create_entry(entry):
            layer_id = entry.get("id")
            if layer_id in created:
                return created[layer_id]

            parent_item = service_item
            parent_id = entry.get("parentLayerId", -1)
            if parent_id in by_id and parent_id != layer_id:
                parent_item = create_entry(by_id[parent_id])

            layer_name = entry.get("name") or f"Capa {layer_id}"
            data_kind = arcgis_data_kind(entry)
            is_group = data_kind == "grupo"
            tree_item = QTreeWidgetItem(parent_item)
            tree_item.setText(0, layer_name)

            if is_group:
                tree_item.setText(1, "Grupo")
                tree_item.setFont(0, self.section_font())
                self.set_item_metadata(tree_item, {
                    "type": "arcgis_group",
                    "stype": service_data["stype"],
                    "url": service_url,
                    "name": layer_name,
                    "institution": service_data["institution"],
                    "category": service_data["category"],
                    "description": "Grupo de subcapas del servicio ArcGIS REST.",
                    **arcgis_metadata_fields(entry, metadata),
                })
            else:
                # MapServer vector sublayers keep the map-layer implementation so
                # importing can fall back to the rendered raster endpoint if needed.
                leaf_type = (
                    "arcgis_vector_layer"
                    if service_kind == "FeatureServer" or entry.get("is_table", False)
                    else "arcgis_map_layer"
                )
                layer_url = _append_rest_path(service_url, layer_id)
                display_type = {"tabla": "Tabla REST", "vectorial": "Vectorial REST",
                                "raster": "Raster REST", "mixto": "Raster/Vectorial REST"}[data_kind]
                tree_item.setText(1, display_type)
                self.set_item_metadata(tree_item, {
                    "type": leaf_type,
                    "stype": leaf_type,
                    "data_kind": data_kind,
                    "service_kind": service_kind,
                    "service_url": service_url,
                    "url": layer_url,
                    "layer_id": layer_id,
                    "name": layer_name,
                    "institution": service_data["institution"],
                    "category": service_data["category"],
                    "description": f"Capa {layer_id} del servicio ArcGIS REST {service_kind}.",
                    "crs_warning": service_data.get("crs_warning", False) or is_psad56_reference(
                        entry.get("spatialReference") or (entry.get("extent") or {}).get("spatialReference")),
                    **arcgis_metadata_fields(entry, metadata),
                })
            if not is_group:
                tree_item.setText(1, self.entry_display_type(tree_item.data(0, Qt.ItemDataRole.UserRole)))
            created[layer_id] = tree_item
            return tree_item

        for entry in entries:
            create_entry(entry)

    def on_item_double_clicked(self, item, column):
        """Expand REST containers or add an individual REST layer."""
        s = item.data(0, Qt.ItemDataRole.UserRole)
        if s is None:
            return
        if s.get("type") in ["server", "folder", "arcgis_service", "arcgis_group", "ogc_service", "wms_group"]:
            item.setExpanded(not item.isExpanded())
        else:
            self.add_selected_layer()

    def update_buttons_state(self, s):
        """Enables/disables buttons and sets metadata description based on selection."""
        selected = self.tree_widget.selectedItems()
        layer_count = sum(1 for item in selected
                          if self.can_add_layer(item.data(0, Qt.ItemDataRole.UserRole) or {}))
        if s is None:
            self.metadata_panel.setHtml(
                "<h3>Explore el catálogo</h3>"
                "<p>Busque una capa o expanda una institución para consultar sus servicios.</p>"
                "<p>Los detalles de su selección aparecerán aquí.</p>"
            )
            self.crs_banner.setVisible(False)
            self.metadata_panel.setToolTip("")
            self.btn_add_layer.setEnabled(False)
            self.btn_add_layer.setText("Añadir al mapa")
            self.btn_register_browser.setEnabled(False)
            self.btn_copy_url.setEnabled(False)
            self.btn_open_browser.setEnabled(False)
            self.btn_service_access.setEnabled(False)
            self.btn_service_access.setText("Configurar acceso privado")
        else:
            service_url = s.get("service_url") or s.get("url", "")
            has_auth = bool(self.auth_config_for_url(service_url))
            self.btn_service_access.setEnabled(bool(self.normalize_auth_scope(service_url)))
            self.btn_service_access.setText(
                "Acceso privado configurado" if has_auth else "Configurar acceso privado"
            )
            ntype = s.get("type", "service")
            self.crs_banner.setVisible(bool(s.get("crs_warning", False)))
            is_container = ntype in self.CONTAINER_TYPES
            if ntype == "ogc_service":
                description = "Expanda el servicio para consultar sus capas WMS."
                kind = "WMS"
            elif is_container:
                description = ("Añada el mapa completo como ráster con la simbología del servidor, o expanda el servicio para seleccionar sus subcapas."
                               if self.is_map_service(s) else "Expanda el servicio para explorar sus carpetas y capas.")
                kind = self.entry_display_type(s)
            else:
                description = s.get("description", "")
                kind = self.entry_display_type(s)
                if ntype == "arcgis_map_layer" and not s.get("is_table"):
                    description += " Para cargar la imagen con la simbología del servidor, use clic derecho → Añadir como mapa ráster."

            name = escape(str(s.get("name", "Sin nombre")))
            institution = escape(str(s.get("institution", "")))
            category = escape(str(s.get("category", "")))
            url = str(s.get("url", ""))
            href = escape(url, quote=True)
            host = escape(urllib.parse.urlsplit(url).netloc or url)
            tags = ", ".join(str(tag) for tag in s.get("tags", []))
            details = f"<p>{escape(str(description))}</p>" if description else ""
            tags_html = f"<p>Etiquetas: {escape(tags)}</p>" if tags else ""
            metadata_facts = []
            protocol = s.get("service_kind") or ("WMS" if s.get("stype") == "wms" else None)
            if protocol:
                metadata_facts.append(f"Conexión: {protocol}")
            if s.get("is_table") or s.get("data_kind") == "tabla":
                metadata_facts.append("Tabla sin geometría")
            elif s.get("geometry_type"):
                geometry = {"esriGeometryPoint": "Puntos", "esriGeometryMultipoint": "Multipuntos",
                            "esriGeometryPolyline": "Líneas", "esriGeometryPolygon": "Polígonos"}.get(
                                s["geometry_type"], str(s["geometry_type"]))
                metadata_facts.append(geometry)
            if type(s.get("field_count")) is int:
                metadata_facts.append(f"{s['field_count']} campo publicado" if s["field_count"] == 1
                                      else f"{s['field_count']} campos publicados")
            spatial_reference = s.get("spatial_reference") or {}
            if isinstance(spatial_reference, dict):
                wkid = spatial_reference.get("latestWkid") or spatial_reference.get("wkid")
                if wkid:
                    metadata_facts.append(f"CRS declarado (WKID): {wkid}")
            facts_html = f"<p>{escape(' · '.join(metadata_facts))}</p>" if metadata_facts else ""
            warnings_html = ("<p><b>Revisar atributos.</b> La fuente publica nombres de campos repetidos.</p>"
                             if "duplicate_field_names" in (s.get("metadata_warnings") or []) else "")
            if set(s.get("metadata_warnings") or []) & {"incomplete_sublayers", "missing_sublayers"}:
                warnings_html += "<p><b>Subcapas no disponibles.</b> El servicio publica referencias a subcapas que no responden.</p>"
            self.metadata_panel.setHtml(
                f"<h3>{name}</h3><p>{institution}</p>"
                f"<p>{category} · {escape(str(kind))}</p>"
                f"{details}{facts_html}{warnings_html}<p><a href='{href}'>{host}</a></p>{tags_html}"
            )
            self.metadata_panel.setToolTip(url)
            self.btn_add_layer.setEnabled(self.can_add_layer(s))
            self.btn_register_browser.setEnabled(ntype != "arcgis_group")
            self.btn_copy_url.setEnabled(True)
            self.btn_open_browser.setEnabled(True)

        self.btn_add_layer.setText(f"Añadir {layer_count} capas" if layer_count > 1 else
                                  "Añadir mapa ráster" if s and self.is_map_service(s) else "Añadir al mapa")
        self.btn_add_layer.setEnabled(layer_count > 0 and not self._loading_layers)
        if len(selected) != 1:
            for control in (self.btn_register_browser, self.btn_copy_url, self.btn_open_browser, self.btn_service_access):
                control.setEnabled(False)
        elif s is not None:
            try:
                connection_root(s.get("stype") or s.get("type"))
            except ValueError:
                self.btn_register_browser.setEnabled(False)

    @staticmethod
    def provider_error(layer):
        if layer is None:
            return "QGIS no creó la capa"
        try:
            summary = layer.error().summary()
            if summary:
                return summary
        except Exception:
            return "el proveedor QGIS no devolvió detalles del error REST"
        return "el proveedor QGIS consideró inválida la fuente ArcGIS REST"

    @staticmethod
    def apply_metadata_crs(layer, metadata):
        if not layer or not layer.isValid() or layer.crs().isValid():
            return
        extent = metadata.get("extent") or metadata.get("fullExtent") or {}
        spatial_ref = metadata.get("spatialReference") or extent.get("spatialReference") or {}
        wkid = spatial_ref.get("latestWkid") or spatial_ref.get("wkid")
        crs = QgsCoordinateReferenceSystem()
        if wkid:
            try:
                crs = QgsCoordinateReferenceSystem.fromEpsgId(int(wkid))
                if not crs.isValid():
                    crs = QgsCoordinateReferenceSystem(f"ESRI:{wkid}")
            except (TypeError, ValueError, OverflowError):
                pass
        wkt = spatial_ref.get("wkt") or spatial_ref.get("wkt2")
        if not crs.isValid() and isinstance(wkt, str) and wkt:
            crs = QgsCoordinateReferenceSystem.fromWkt(wkt)
        if crs.isValid():
            layer.setCrs(crs)

    def create_arcgis_vector_layer(self, layer_url, name, metadata=None):
        uri = QgsDataSourceUri()
        uri.setParam("url", _clean_rest_url(layer_url))
        authcfg = self.auth_config_for_url(layer_url)
        if authcfg:
            uri.setAuthConfigId(authcfg)
        layer = QgsVectorLayer(uri.uri(False), name, "arcgisfeatureserver")
        self.apply_metadata_crs(layer, metadata or {})
        return layer

    def create_arcgis_map_layer(self, service_url, layer_id, name, metadata=None):
        uri = QgsDataSourceUri()
        uri.setParam("url", _clean_rest_url(service_url))
        authcfg = self.auth_config_for_url(service_url)
        if authcfg:
            uri.setAuthConfigId(authcfg)
        if layer_id is not None:
            uri.setParam("layer", str(layer_id))
        uri.setParam("format", "png32")
        layer = QgsRasterLayer(uri.uri(False), name, "arcgismapserver")
        self.apply_metadata_crs(layer, metadata or {})
        return layer

    def create_arcgis_image_layer(self, url, name, metadata=None):
        uri = QgsDataSourceUri()
        uri.setParam("url", _clean_rest_url(url))
        authcfg = self.auth_config_for_url(url)
        if authcfg:
            uri.setAuthConfigId(authcfg)
        providers = QgsProviderRegistry.instance().providerList()
        provider = "arcgisimageserver" if "arcgisimageserver" in providers else "arcgismapserver"
        layer = QgsRasterLayer(uri.uri(False), name, provider)
        if not layer.isValid() and provider != "arcgismapserver":
            layer = QgsRasterLayer(uri.uri(False), name, "arcgismapserver")
        self.apply_metadata_crs(layer, metadata or {})
        return layer

    def create_wms_layer(self, service_url, layer_name, name, crs_options=None):
        """Create a QGIS WMS raster layer for one named GetCapabilities entry."""
        options = list(crs_options or [])
        project_authid = QgsProject.instance().crs().authid()
        preferred_crs = next(
            (
                candidate for candidate in (project_authid, "EPSG:3857", "EPSG:4326")
                if candidate and candidate in options
            ),
            options[0] if options else (project_authid or "EPSG:4326"),
        )
        uri = QgsDataSourceUri()
        uri.setParam("url", service_url)
        uri.setParam("layers", layer_name)
        uri.setParam("styles", "")
        uri.setParam("format", "image/png")
        uri.setParam("crs", preferred_crs)
        authcfg = self.auth_config_for_url(service_url)
        if authcfg:
            uri.setAuthConfigId(authcfg)
        return QgsRasterLayer(bytes(uri.encodedUri()).decode("utf-8"), name, "wms")

    def _instantiate_layer(self, s):
        """Helper to create and validate a layer object from its metadata dictionary."""
        name = s.get("name", "Capa")
        layer_type = s.get("type")
        attempts = []
        layer = None
        metadata = {}

        try:
            if self.is_map_service(s):
                layer = self.create_arcgis_map_layer(s["url"], None, name)
                if not layer.isValid():
                    attempts.append(f"Mapa ráster MapServer: {self.provider_error(layer)}")

            elif layer_type == "arcgis_vector_layer":
                layer = self.create_arcgis_vector_layer(s["url"], name)
                if not layer.isValid():
                    attempts.append(f"Vector REST: {self.provider_error(layer)}")

            elif layer_type == "arcgis_map_layer":
                try:
                    metadata = self.fetch_arcgis_json(s["url"], timeout=12)
                except Exception as exc:
                    attempts.append(f"Metadatos REST: {exc}")

                published_kind = arcgis_data_kind(metadata)
                if published_kind == "grupo":
                    attempts.append("Este ID corresponde ahora a un grupo de capas. Expanda el servicio y seleccione una subcapa actualizada.")
                    return None, attempts
                if published_kind == "tabla":
                    layer = self.create_arcgis_vector_layer(s["url"], name, metadata)
                    if not layer.isValid():
                        attempts.append(f"Tabla REST: {self.provider_error(layer)}")
                    return layer, attempts

                geometry_type = metadata.get("geometryType")
                layer_kind = str(metadata.get("type", "")).lower()
                capabilities = str(metadata.get("capabilities", "")).lower()
                queryable_vector = bool(geometry_type) and (
                    not capabilities or "query" in capabilities
                ) and "raster" not in layer_kind

                if queryable_vector and not s.get("prefer_raster"):
                    layer = self.create_arcgis_vector_layer(s["url"], name, metadata)
                    if not layer.isValid():
                        attempts.append(f"Vector REST: {self.provider_error(layer)}")

                if not layer or not layer.isValid():
                    layer = self.create_arcgis_map_layer(
                        s["service_url"], s["layer_id"], name, metadata
                    )
                    if not layer.isValid():
                        attempts.append(f"Raster MapServer: {self.provider_error(layer)}")

            elif layer_type == "arcgis_raster_layer" or s.get("service_kind") == "ImageServer":
                try:
                    metadata = self.fetch_arcgis_json(s["url"], timeout=12)
                except Exception as exc:
                    attempts.append(f"Metadatos REST: {exc}")
                layer = self.create_arcgis_image_layer(s["url"], name, metadata)
                if not layer.isValid():
                    attempts.append(f"Raster ImageServer: {self.provider_error(layer)}")

            elif layer_type == "wms_layer":
                layer = self.create_wms_layer(
                    s["service_url"],
                    s["layer_name"],
                    name,
                    s.get("crs_options"),
                )
                if not layer.isValid():
                    attempts.append(f"WMS: {self.provider_error(layer)}")

            else:
                attempts.append(f"Tipo no importable: {layer_type}")

        except Exception as exc:
            attempts.append(str(exc))

        return layer, attempts

    def add_selected_layer(self, as_raster=False):
        """Load a stable selection snapshot and tolerate nested GUI events."""
        if not self._ui_available() or self._loading_layers:
            return
        layers = []
        for item in self.tree_widget.selectedItems():
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if self.can_add_layer(data):
                layers.append(dict(data, prefer_raster=bool(as_raster)))
        if not layers:
            return

        from qgis.PyQt.QtWidgets import QApplication
        self._loading_layers = True
        self.btn_add_layer.setEnabled(False)
        self._layer_progress = (0, len(layers), "Preparando capas…")
        self._update_progress()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        added_count = 0
        failed_items = []
        try:
            for index, data in enumerate(layers):
                if not self._ui_available():
                    break
                name = data.get("name", "Capa")
                self._layer_progress = (index, len(layers), f"Cargando ({index + 1}/{len(layers)}): {name[:35]}…")
                self._update_progress()
                QApplication.processEvents()
                if not self._ui_available():
                    break
                try:
                    layer, attempts = self._instantiate_layer(data)
                except Exception as exc:
                    layer, attempts = None, [str(exc)]
                if not self._ui_available():
                    break
                if layer is not None and layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    added_count += 1
                else:
                    failed_items.append((name, "; ".join(attempts) or "error de proveedor"))
            self._layer_progress = (len(layers), len(layers), "Carga completada")
        finally:
            self._loading_layers = False
            QApplication.restoreOverrideCursor()
            if self._ui_available():
                self._update_progress()
                selected = self.tree_widget.selectedItems()
                self.update_buttons_state(selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None)

        if not self._ui_available():
            return
        if len(layers) == 1 and added_count:
            self.iface.messageBar().pushMessage(
                "PeruSpatial Hub", f"Capa '{layers[0].get('name', '')}' añadida correctamente.",
                level=3, duration=4)
        else:
            message = f"Se añadieron {added_count} de {len(layers)} capas al mapa."
            if failed_items:
                message += f" ({len(failed_items)} fallaron)"
            self.iface.messageBar().pushMessage("PeruSpatial Hub", message,
                level=3 if added_count else 2, duration=5)
        if failed_items:
            errors = "\n".join(f"- {name}: {detail[:500]}" for name, detail in failed_items[:10])
            if len(failed_items) > 10:
                errors += f"\n… y {len(failed_items) - 10} errores adicionales."
            QMessageBox.warning(self, "Capas no cargadas",
                f"Se añadieron {added_count} de {len(layers)} capas.\n\n{errors}\n\n"
                "Revise la disponibilidad del servicio y el proveedor de QGIS.")

    def register_selected_connection(self):
        """Registers the selected service in QGIS Settings for Browser panel integration."""
        selected_items = self.tree_widget.selectedItems()
        if len(selected_items) != 1:
            return
        
        s = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if s is None:
            return

        name = s["name"]
        url = s.get("service_url", s["url"])
        stype = s.get("stype", s.get("type"))
        if stype in ["arcgis_map_layer", "arcgis_raster_layer", "arcgis_imageserver"]:
            stype = "arcgis_mapserver"
        elif stype == "arcgis_vector_layer":
            stype = (
                "arcgisfeatureserver"
                if s.get("service_kind") == "FeatureServer"
                else "arcgis_mapserver"
            )

        try:
            name = self.write_connection(name, url, stype, self.auth_config_for_url(url))
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo registrar la conexión", str(exc))
            return

        connection_section = "WMS/WMTS" if stype == "wms" else "ArcGIS REST"

        QMessageBox.information(
            self,
            "Conexión Registrada",
            f"La conexión '{name}' ha sido agregada con éxito al panel Explorador de QGIS.\n\n"
            f"Puede encontrarla en la sección nativa {connection_section}."
        )

    def register_all_connections(self):
        """Registers all database services in QGIS Settings at once."""
        reply = QMessageBox.question(
            self,
            "Registrar Todos los Servicios",
            "¿Desea registrar todas las conexiones verificadas del catálogo en el panel Explorador de QGIS?\n\n"
            "Esto creará conexiones nativas organizadas para que pueda explorar todo el catálogo del estado "
            "peruano directamente desde el panel de QGIS.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            count = 0
            for s in self.live_servers:
                full_name = f"{s['institution']} - {s['name']}"
                self.write_connection(
                    full_name,
                    s["url"],
                    s["stype"],
                    self.auth_config_for_url(s["url"]),
                )
                count += 1
            
            self.iface.reloadConnections()

            QMessageBox.information(
                self,
                "Registro Completo",
                f"Se han registrado {count} conexiones en el panel Explorador de QGIS.\n\n"
                "Revise las secciones 'ArcGIS REST Servers' y 'WMS/WMTS' del panel Explorador."
            )

    def write_connection(self, name, url, stype, authcfg=""):
        """Register an immediately usable native connection without clobbering others."""
        saved_name = register_connection(
            QgsSettings(), name, url, stype, authcfg,
            anonymous_override=self.auth_scope_for_url(url) == self.NO_AUTH_SCOPE)
        self.iface.reloadConnections()
        return saved_name

    def copy_selected_url(self):
        """Copies the URL of the selected service to the clipboard."""
        selected_items = self.tree_widget.selectedItems()
        if len(selected_items) != 1:
            return
        
        s = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if s is not None:
            from qgis.PyQt.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(s["url"])
            self.iface.messageBar().pushMessage(
                "PeruSpatial Hub",
                "URL copiada al portapapeles.",
                level=3, # Success
                duration=2
            )

    def open_selected_web(self):
        """Opens the selected service's REST/WMS endpoint page in default web browser."""
        selected_items = self.tree_widget.selectedItems()
        if len(selected_items) != 1:
            return
        
        s = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if s is not None:
            webbrowser.open(s["url"])
