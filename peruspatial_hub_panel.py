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

from qgis.PyQt.QtCore import Qt, QTimer, QUrl, QByteArray, QXmlStreamReader
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QPushButton, QToolButton,
    QLabel, QTextBrowser, QMessageBox, QSplitter, QDialog, QDialogButtonBox,
    QMenu, QProgressBar, QHeaderView
)
from qgis.PyQt.QtGui import QFont, QColor, QPalette
from qgis.core import (
    QgsSettings, QgsRasterLayer, QgsVectorLayer, QgsProject, QgsDataSourceUri,
    QgsCoordinateReferenceSystem, QgsNetworkAccessManager, QgsApplication, QgsTask
)
from qgis.gui import QgsAuthConfigSelect

from .peruspatial_hub_urls import (
    append_rest_path as _append_rest_path,
    clean_rest_url as _clean_rest_url,
    service_url as _service_url,
    url_with_json as _url_with_json,
    wms_capabilities_url as _wms_capabilities_url,
)
from .peruspatial_hub_catalog import (
    load_catalog,
    normalize_search_text as _normalize_catalog_text,
    search_catalog,
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

    def __init__(self, parent=None):
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
        details.setHtml(
            "<p>Notas de la revisión incluida en el catálogo. Para consultar la "
            "disponibilidad actual, use <b>Herramientas → Verificar servidores</b>.</p>"
            "<h3>OEFA</h3><p>El directorio público PIFA está integrado en el catálogo.</p>"
            "<h3>SUNARP</h3><p>El visor BGR requiere identificación y captcha. "
            "No se identificó un directorio REST de acceso anónimo.</p>"
            "<h3>CENEPRED</h3><p>En la revisión, el acceso público de SIGRID no pudo "
            "comunicarse con su servidor interno.</p>"
            "<h3>COFOPRI</h3><p>La revisión encontró errores de certificado TLS y "
            "una ruta REST con respuesta HTTP 404.</p>"
            "<h3>Servicios con acceso privado</h3>"
            "<p>Seleccione un servicio HTTPS y use <b>Herramientas → Configurar acceso "
            "privado</b>. Las credenciales se administran en QGIS. La autenticación "
            "no resuelve fallas de disponibilidad ni permite omitir captchas.</p>"
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

        catalog_path = os.path.join(self.plugin_dir or "", "catalog", "catalog.json")
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
        """A compact, left-aligned identity above the working catalog."""
        header = QWidget()
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(3)
        title = QLabel("PeruSpatial Hub")
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        subtitle = QLabel("Datos geoespaciales del Perú")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
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
        self.tree_widget.setHeaderLabels(["Catálogo / Institución", "Tipo"])
        self.tree_widget.header().setStretchLastSection(False)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.tree_widget.setColumnWidth(1, 100)
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

    def show_about_dialog(self):
        """Opens the About dialog with developer information and links."""
        dialog = AboutDialog(self, self.plugin_dir)
        dialog.exec()

    def show_service_status_dialog(self):
        """Shows the research status of unavailable or restricted services."""
        dialog = ServiceStatusDialog(self)
        dialog.exec()

    # ------------------------------------------------------------------
    #  Context menu
    # ------------------------------------------------------------------

    CONTAINER_TYPES = {"server", "folder", "arcgis_service", "arcgis_group", "ogc_service", "wms_group"}
    LAYER_TYPES = {"arcgis_map_layer", "arcgis_vector_layer", "arcgis_raster_layer", "wms_layer"}

    def show_context_menu(self, position):
        """Show a right-click context menu with actions appropriate for the selected node."""
        item = self.tree_widget.itemAt(position)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return

        menu = QMenu(self)
        ntype = data.get("type", "")

        if ntype in self.CONTAINER_TYPES:
            menu.addAction("Expandir / contraer", lambda: item.setExpanded(not item.isExpanded()))
            if data.get("is_loaded", False):
                menu.addAction("Actualizar contenido", lambda: self.refresh_node(item))
            menu.addSeparator()
            if ntype != "arcgis_group":
                menu.addAction("Registrar conexión", self.register_selected_connection)
            menu.addAction("Copiar URL", self.copy_selected_url)
            menu.addAction("Abrir en navegador", self.open_selected_web)
        elif ntype in self.LAYER_TYPES:
            selected = self.tree_widget.selectedItems()
            if len(selected) > 1:
                layer_count = sum(
                    1 for it in selected
                    if (it.data(0, Qt.ItemDataRole.UserRole) or {}).get("type") in self.LAYER_TYPES
                )
                menu.addAction(f"Añadir {layer_count} capas al Mapa", self.add_selected_layer)
            else:
                menu.addAction("Añadir al mapa", self.add_selected_layer)
            menu.addSeparator()
            menu.addAction("Copiar URL", self.copy_selected_url)
            menu.addAction("Abrir en navegador", self.open_selected_web)
            menu.addSeparator()
            if self._is_favorite(data):
                menu.addAction("Quitar de favoritos", lambda: self.remove_from_favorites(item))
            else:
                menu.addAction("Añadir a favoritos", lambda: self.add_to_favorites(item))

        if self.normalize_auth_scope(data.get("service_url") or data.get("url", "")):
            menu.addSeparator()
            menu.addAction("Configurar acceso privado", self.configure_selected_service_access)

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
        item.setData(0, Qt.ItemDataRole.UserRole, data)
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
        return (data.get("url", "") or "") + "|" + (data.get("name", "") or "")

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
        return favorites if isinstance(favorites, list) else []

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
            if k not in {"_search_text", "_catalog_result", "is_loaded"}
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
            fav_item.setText(1, self.friendly_type(fav.get("stype", fav.get("type", ""))))
            fav_item.setToolTip(0, fav.get("url", ""))
            fav_item.setData(0, Qt.ItemDataRole.UserRole, fav)
            # If it is a container type, allow live expansion
            if fav.get("type") in self.CONTAINER_TYPES:
                fav["is_loaded"] = False
                fav_item.setData(0, Qt.ItemDataRole.UserRole, fav)
                dummy = QTreeWidgetItem(fav_item)
                dummy.setText(0, "Expandir para consultar en vivo...")

    # ------------------------------------------------------------------
    #  Health check
    # ------------------------------------------------------------------

    def check_all_servers_health(self):
        """Test every live server without blocking QGIS' interface thread."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Verificando servidores en segundo plano...")
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
                        self.fetch_arcgis_json(
                            server["url"],
                            timeout=8,
                            attempts=1,
                            authcfg=auth_configs[server["url"]],
                        )
                    else:
                        self.read_service_https(
                            _wms_capabilities_url(server["url"]),
                            timeout=8,
                            headers={
                                "User-Agent": PLUGIN_USER_AGENT,
                                "Accept": "application/xml,text/xml",
                            },
                            authcfg=auth_configs[server["url"]],
                        )
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
            self.progress_bar.setVisible(False)
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
        task.progressChanged.connect(
            lambda value: self.progress_bar.setValue(int(value))
            if not self._shutting_down else None
        )
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
            if cls.normalize_auth_scope(scope) and str(authcfg).strip()
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

    def auth_config_for_url(self, url):
        """Return the auth config for the most specific matching service scope."""
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
        matched_authcfg = max(matches, default=(0, ""))[1]
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
        if not selected_items:
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
        self.search_results_root.setData(0, Qt.ItemDataRole.UserRole, None)
        self.search_results_root.setHidden(True)
        
        # The old fixed layer URLs contained many retired services. Start from
        # live repository roots and discover their current services/layers.
        explorer_root = QTreeWidgetItem(self.tree_widget)
        explorer_root.setText(0, "Servidores disponibles")
        explorer_root.setFont(0, self.section_font())
        explorer_root.setData(0, Qt.ItemDataRole.UserRole, None)


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
            server_item.setText(1, "ArcGIS REST" if is_arcgis else "WMS")
            server_item.setData(0, Qt.ItemDataRole.UserRole, {
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
        self.favorites_root.setData(0, Qt.ItemDataRole.UserRole, None)
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
            "arcgis_mapserver": "Raster/Vectorial REST",
            "arcgisfeatureserver": "Vectorial REST",
            "arcgis_imageserver": "Raster REST",
            "arcgis_map_layer": "Capa REST",
            "arcgis_vector_layer": "Vectorial REST",
            "arcgis_raster_layer": "Raster REST",
            "wms": "Servidor WMS",
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

        for i in range(self.tree_widget.topLevelItemCount()):
            self.filter_tree_item(
                self.tree_widget.topLevelItem(i), search_text, selected_category
            )

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
            item = QTreeWidgetItem(self.search_results_root)
            institution = data.get("institution", "")
            item.setText(0, f"{institution} — {data.get('name', 'Sin nombre')}")
            item.setText(
                1,
                entry.get("display_type")
                or self.friendly_type(data.get("stype", data.get("type", ""))),
            )
            item.setToolTip(0, entry.get("path", data.get("url", "")))
            item.setData(0, Qt.ItemDataRole.UserRole, data)

            if data.get("type") in {"server", "folder", "arcgis_service", "ogc_service"}:
                data["is_loaded"] = False
                item.setData(0, Qt.ItemDataRole.UserRole, data)
                dummy = QTreeWidgetItem(item)
                dummy.setText(0, "Expandir para consultar en vivo...")

        self.search_results_root.setExpanded(True)

    def apply_catalog_search(self):
        """Apply a fully local search; this method never performs network I/O."""
        if not hasattr(self, "search_results_root"):
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
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            self.update_buttons_state(None)
            return

        item = selected_items[0]
        s = item.data(0, Qt.ItemDataRole.UserRole)
        
        self.update_buttons_state(s)

    def on_item_expanded(self, item):
        """Called when a tree node is expanded. Loads subfolders/services dynamically."""
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
        node_data["is_loading"] = True
        item.setData(0, Qt.ItemDataRole.UserRole, node_data)
        item.takeChildren()
        loading_node = QTreeWidgetItem(item)
        loading_node.setText(0, "Cargando...")
        if self._search_cancelled or not self.isVisible():
            if loading_node.parent() is item:
                item.removeChild(loading_node)
            node_data["is_loading"] = False
            item.setData(0, Qt.ItemDataRole.UserRole, node_data)
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
                    inst = node_data["institution"]
                    cat = node_data["category"]

                    # Folders
                    for f in payload.get("folders", []):
                        folder_name = f
                        furl = _append_rest_path(url, folder_name)

                        f_item = QTreeWidgetItem(item)
                        f_item.setText(0, folder_name)
                        f_item.setText(1, "Carpeta REST")
                        f_item.setFont(0, self.section_font())
                        f_item.setData(0, Qt.ItemDataRole.UserRole, {
                            "type": "folder",
                            "stype": "arcgis_rest",
                            "url": furl,
                            "is_loaded": False,
                            "name": folder_name,
                            "institution": inst,
                            "category": cat,
                        })
                        dummy = QTreeWidgetItem(f_item)
                        dummy.setText(0, "Expandir para explorar...")

                    # Services
                    for s in payload.get("services", []):
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
                        s_item.setData(0, Qt.ItemDataRole.UserRole, {
                            "type": "arcgis_raster_layer" if is_image else "arcgis_service",
                            "stype": friendly_type,
                            "service_kind": stype_str,
                            "url": surl,
                            "name": sname_short,
                            "institution": inst,
                            "category": cat,
                            "description": f"Servicio REST {stype_str} en vivo provisto por {inst}.",
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
                item.setData(0, Qt.ItemDataRole.UserRole, node_data)
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
        for task in tuple(self._background_tasks):
            task.cancel()
        self._background_tasks.clear()

    @staticmethod
    def parse_wms_layer_catalog(payload):
        """Parse WMS layer names with Qt's streaming XML reader."""
        reader = QXmlStreamReader(QByteArray(payload))
        document_depth = 0
        capability_depth = None
        layer_stack = []
        root_layers = []

        while not reader.atEnd():
            reader.readNext()

            if reader.isDTD() or reader.isEntityReference():
                raise RuntimeError(
                    "GetCapabilities WMS contiene DTD o entidades XML no permitidas"
                )

            if reader.isStartElement():
                document_depth += 1
                element_name = reader.name().toString()

                if element_name == "Capability":
                    capability_depth = document_depth
                    continue

                if element_name == "Layer" and capability_depth is not None:
                    layer_data = {
                        "title": "",
                        "name": "",
                        "crs": [],
                        "children": [],
                        "_depth": document_depth,
                    }
                    if layer_stack:
                        layer_stack[-1]["children"].append(layer_data)
                    else:
                        root_layers.append(layer_data)
                    layer_stack.append(layer_data)
                    continue

                if (
                    layer_stack
                    and document_depth == layer_stack[-1]["_depth"] + 1
                    and element_name in ("Title", "Name", "CRS", "SRS")
                ):
                    value = reader.readElementText().strip()
                    if element_name == "Title":
                        layer_stack[-1]["title"] = value
                    elif element_name == "Name":
                        layer_stack[-1]["name"] = value
                    elif value:
                        layer_stack[-1]["crs"].append(value)
                    # readElementText leaves the reader on this element's end token.
                    document_depth -= 1

            elif reader.isEndElement():
                element_name = reader.name().toString()
                if (
                    element_name == "Layer"
                    and layer_stack
                    and layer_stack[-1]["_depth"] == document_depth
                ):
                    layer_stack.pop()
                if element_name == "Capability":
                    capability_depth = None
                document_depth -= 1

        if reader.hasError():
            raise RuntimeError(
                f"GetCapabilities WMS no devolvió XML válido: {reader.errorString()}"
            )
        if not root_layers:
            raise RuntimeError("GetCapabilities WMS no contiene un catálogo de capas")

        for root_layer in root_layers:
            stack = [root_layer]
            while stack:
                layer_data = stack.pop()
                layer_data.pop("_depth", None)
                stack.extend(layer_data["children"])
        return root_layers[0]

    def populate_wms_layers(self, service_item, service_data, payload):
        """Populate a WMS catalog with importable named layers from GetCapabilities."""
        root_layer = self.parse_wms_layer_catalog(payload)

        service_url = _clean_rest_url(service_data["url"])
        institution = service_data["institution"]
        category = service_data["category"]
        created_layers = 0

        def add_layer_node(layer_data, parent_item, inherited_crs):
            nonlocal created_layers
            title = layer_data["title"] or "Grupo WMS"
            layer_name = layer_data["name"]
            own_crs = layer_data["crs"]
            available_crs = list(dict.fromkeys(own_crs or inherited_crs))
            children = layer_data["children"]

            if layer_name:
                tree_item = QTreeWidgetItem(parent_item)
                tree_item.setText(0, title)
                tree_item.setText(1, "Capa WMS")
                tree_item.setData(0, Qt.ItemDataRole.UserRole, {
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
                    group_item.setText(1, "Grupo WMS")
                    group_item.setFont(0, self.section_font())
                    group_item.setData(0, Qt.ItemDataRole.UserRole, {
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
        service_kind = service_data.get("service_kind") or self.service_kind_from_url(
            service_url, service_data.get("stype")
        )
        entries = []
        for layer_info in metadata.get("layers", []):
            entry = dict(layer_info)
            entry["is_table"] = False
            entries.append(entry)
        for table_info in metadata.get("tables", []):
            entry = dict(table_info)
            entry["is_table"] = True
            entries.append(entry)

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
            sublayer_ids = entry.get("subLayerIds")
            is_group = entry.get("type") == "Group Layer" or bool(sublayer_ids)
            tree_item = QTreeWidgetItem(parent_item)
            tree_item.setText(0, layer_name)

            if is_group:
                tree_item.setText(1, "Grupo REST")
                tree_item.setFont(0, self.section_font())
                tree_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "arcgis_group",
                    "stype": service_data["stype"],
                    "url": service_url,
                    "name": layer_name,
                    "institution": service_data["institution"],
                    "category": service_data["category"],
                    "description": "Grupo de subcapas del servicio ArcGIS REST.",
                })
            else:
                layer_type_name = str(entry.get("type", "")).casefold()
                has_geometry = bool(entry.get("geometryType"))
                is_vector = (
                    service_kind == "FeatureServer"
                    or entry.get("is_table", False)
                    or has_geometry
                )
                is_raster = "raster" in layer_type_name or "mosaic" in layer_type_name
                # MapServer vector sublayers keep the map-layer implementation so
                # importing can fall back to the rendered raster endpoint if needed.
                leaf_type = (
                    "arcgis_vector_layer"
                    if service_kind == "FeatureServer" or entry.get("is_table", False)
                    else "arcgis_map_layer"
                )
                layer_url = _append_rest_path(service_url, layer_id)
                if is_vector:
                    display_type = "Vectorial REST"
                    data_kind = "vectorial"
                elif is_raster:
                    display_type = "Raster REST"
                    data_kind = "raster"
                else:
                    display_type = "Raster/Vectorial REST"
                    data_kind = "mixto"
                tree_item.setText(1, display_type)
                tree_item.setData(0, Qt.ItemDataRole.UserRole, {
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
                    "crs_warning": service_data.get("crs_warning", False),
                })
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
            selected_items = self.tree_widget.selectedItems()
            if len(selected_items) > 1:
                layer_count = sum(
                    1 for it in selected_items
                    if (it.data(0, Qt.ItemDataRole.UserRole) or {}).get("type") in self.LAYER_TYPES
                )
                if layer_count > 1:
                    self.btn_add_layer.setText(f"Añadir {layer_count} capas")
                    self.btn_add_layer.setEnabled(True)
                else:
                    self.btn_add_layer.setText("Añadir al mapa")
            else:
                self.btn_add_layer.setText("Añadir al mapa")
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
                description = "Expanda el servicio para explorar sus carpetas y capas."
                kind = self.friendly_type(s.get("stype", ntype))
            else:
                description = s.get("description", "")
                kind = self.friendly_type(s.get("stype", ntype))

            name = escape(str(s.get("name", "Sin nombre")))
            institution = escape(str(s.get("institution", "")))
            category = escape(str(s.get("category", "")))
            url = str(s.get("url", ""))
            href = escape(url, quote=True)
            host = escape(urllib.parse.urlsplit(url).netloc or url)
            tags = ", ".join(str(tag) for tag in s.get("tags", []))
            details = f"<p>{escape(str(description))}</p>" if description else ""
            tags_html = f"<p>Etiquetas: {escape(tags)}</p>" if tags else ""
            self.metadata_panel.setHtml(
                f"<h3>{name}</h3><p>{institution}</p>"
                f"<p>{category} · {escape(str(kind))}</p>"
                f"{details}<p><a href='{href}'>{host}</a></p>{tags_html}"
            )
            self.metadata_panel.setToolTip(url)
            self.btn_add_layer.setEnabled(not is_container)
            self.btn_register_browser.setEnabled(ntype != "arcgis_group")
            self.btn_copy_url.setEnabled(True)
            self.btn_open_browser.setEnabled(True)

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
        if not wkid:
            return
        crs = QgsCoordinateReferenceSystem.fromEpsgId(int(wkid))
        if not crs.isValid():
            crs = QgsCoordinateReferenceSystem(f"ESRI:{wkid}")
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
        layer = QgsRasterLayer(uri.uri(False), name, "arcgisimageserver")
        if not layer.isValid():
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
        return QgsRasterLayer(uri.uri(False), name, "wms")

    def _instantiate_layer(self, s):
        """Helper to create and validate a layer object from its metadata dictionary."""
        name = s.get("name", "Capa")
        layer_type = s.get("type")
        attempts = []
        layer = None
        metadata = {}

        try:
            if layer_type == "arcgis_vector_layer":
                layer = self.create_arcgis_vector_layer(s["url"], name)
                if not layer.isValid():
                    attempts.append(f"Vector REST: {self.provider_error(layer)}")

            elif layer_type == "arcgis_map_layer":
                try:
                    metadata = self.fetch_arcgis_json(s["url"], timeout=12)
                except Exception as exc:
                    attempts.append(f"Metadatos REST: {exc}")

                geometry_type = metadata.get("geometryType")
                layer_kind = str(metadata.get("type", "")).lower()
                capabilities = str(metadata.get("capabilities", "")).lower()
                queryable_vector = bool(geometry_type) and (
                    not capabilities or "query" in capabilities
                ) and "raster" not in layer_kind

                if queryable_vector:
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

    def add_selected_layer(self):
        """Add native ArcGIS REST or WMS layer(s) to the map. Supports multi-selection."""
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            return

        valid_items = [
            item for item in selected_items
            if item.data(0, Qt.ItemDataRole.UserRole)
            and item.data(0, Qt.ItemDataRole.UserRole).get("type") in self.LAYER_TYPES
        ]
        if not valid_items:
            return

        from qgis.PyQt.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(valid_items))
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        added_count = 0
        failed_items = []

        try:
            for idx, item in enumerate(valid_items):
                s = item.data(0, Qt.ItemDataRole.UserRole)
                name = s.get("name", "Capa")
                self.progress_bar.setFormat(f"Cargando ({idx + 1}/{len(valid_items)}): {name[:25]}...")
                self.progress_bar.setValue(idx)
                QApplication.processEvents()

                layer, attempts = self._instantiate_layer(s)
                if layer and layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    added_count += 1
                else:
                    detail = "; ".join(attempts) or "error de proveedor"
                    failed_items.append((name, detail))

            self.progress_bar.setValue(len(valid_items))
        finally:
            self.progress_bar.setVisible(False)
            QApplication.restoreOverrideCursor()

        if len(valid_items) == 1:
            if added_count == 1:
                name = valid_items[0].data(0, Qt.ItemDataRole.UserRole).get("name", "")
                self.iface.messageBar().pushMessage(
                    "PeruSpatial Hub",
                    f"Capa '{name}' añadida correctamente.",
                    level=3,
                    duration=4,
                )
            else:
                name, detail = failed_items[0]
                QMessageBox.warning(
                    self,
                    "Error al importar capa",
                    f"No se pudo cargar la capa '{name}'.\n\n- {detail}\n\n"
                    "Revise la disponibilidad del servicio y la compatibilidad del proveedor QGIS.",
                )
        else:
            msg = f"Se añadieron {added_count} de {len(valid_items)} capas al mapa."
            if failed_items:
                msg += f" ({len(failed_items)} fallaron)"
            self.iface.messageBar().pushMessage(
                "PeruSpatial Hub",
                msg,
                level=3 if added_count > 0 else 2,
                duration=5,
            )
            if failed_items and added_count == 0:
                errors_text = "\n".join(f"- {n}: {d}" for n, d in failed_items[:10])
                QMessageBox.warning(
                    self,
                    "Error en carga por lotes",
                    f"No se pudo cargar ninguna de las capas seleccionadas:\n\n{errors_text}",
                )

    def register_selected_connection(self):
        """Registers the selected service in QGIS Settings for Browser panel integration."""
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
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

        self.write_connection(name, url, stype, self.auth_config_for_url(url))

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
        """Writes the actual connection settings to QSettings."""
        settings = QgsSettings()
        
        if stype in ["arcgis_mapserver", "arcgisfeatureserver", "arcgis_imageserver", "arcgis_rest"]:
            if stype == "arcgisfeatureserver":
                key = f"qgis/connections-arcgisfeatureserver/{name}/"
            else:
                key = f"qgis/connections-arcgismapserver/{name}/"
            
            settings.setValue(key + "url", url)
            settings.setValue(key + "authcfg", authcfg or "")
        elif stype == "wms":
            key = f"qgis/connections-wms/{name}/"
            settings.setValue(key + "url", url)
            settings.setValue(key + "authcfg", authcfg or "")
        self.iface.reloadConnections()

    def copy_selected_url(self):
        """Copies the URL of the selected service to the clipboard."""
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
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
        if not selected_items:
            return
        
        s = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if s is not None:
            webbrowser.open(s["url"])
