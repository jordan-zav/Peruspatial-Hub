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

from qgis.PyQt.QtCore import Qt, QTimer, QUrl, QByteArray, QXmlStreamReader
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QPushButton, QToolButton,
    QLabel, QTextBrowser, QMessageBox, QSplitter, QDialog, QDialogButtonBox,
    QMenu, QProgressBar
)
from qgis.PyQt.QtGui import QFont, QColor, QPixmap
from qgis.core import (
    QgsSettings, QgsRasterLayer, QgsVectorLayer, QgsProject, QgsDataSourceUri,
    QgsCoordinateReferenceSystem, QgsNetworkAccessManager
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
        layout.setContentsMargins(30, 30, 30, 20)
        layout.setSpacing(15)

        logo_label = QLabel()
        logo_path = os.path.join(plugin_dir, "logo_dev.png") if plugin_dir else ""
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaledToHeight(80, Qt.TransformationMode.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)

        title = QLabel("<h2>PeruSpatial Hub</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Desarrollado por <b>Jordan Zavaleta (GisGeo Dev)</b><br>"
            "<a href='mailto:jordanzav@gisgeo.dev' style='text-decoration: none; color: #1976d2;'>jordanzav@gisgeo.dev</a>"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setOpenExternalLinks(True)
        layout.addWidget(subtitle)

        links = QLabel(
            "<a href='https://gisgeo.dev' style='text-decoration: none; color: #1976d2;'>Sitio Web: gisgeo.dev</a><br><br>"
            "<a href='https://www.linkedin.com/in/jordan-zav/' style='text-decoration: none; color: #1976d2;'>LinkedIn Profile</a>"
        )
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links.setOpenExternalLinks(True)
        layout.addWidget(links)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.setStyleSheet(
            "QDialog { background-color: white; } QLabel { color: #333; }"
        )


class ServiceStatusDialog(QDialog):
    """Explains why researched institutions may not appear in the catalog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Estado de servicios investigados")
        self.setMinimumSize(560, 430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(10)

        title = QLabel("<h2>Servicios investigados</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        details = QTextBrowser()
        details.setOpenExternalLinks(True)
        details.setHtml(
            "<p>PeruSpatial Hub revisó estas instituciones. Si alguna no aparece como "
            "conexión disponible, no significa que haya sido omitida sin investigación.</p>"
            "<ul>"
            "<li><b>OEFA:</b> el directorio público PIFA está operativo y ya se encuentra "
            "integrado en el catálogo.</li>"
            "<li><b>SUNARP:</b> el Visor BGR solicita DNI, fecha de emisión y captcha. "
            "No se encontró un directorio REST anónimo verificado para integrarlo como "
            "las demás conexiones.</li>"
            "<li><b>CENEPRED:</b> SIGRID dispone de acceso de usuario, pero actualmente "
            "el ArcGIS Web Adaptor público informa que no puede comunicarse con su "
            "servidor interno. Iniciar sesión no corrige esa falla del servicio REST.</li>"
            "<li><b>COFOPRI:</b> el servidor conocido presenta problemas de validación "
            "del certificado TLS y la ruta REST consultada responde HTTP 404. Por "
            "seguridad, el plugin no desactiva la validación de certificados.</li>"
            "</ul>"
            "<p><b>Acceso privado disponible:</b> cualquier servicio HTTPS del catálogo "
            "puede vincularse a una configuración de autenticación de QGIS. Esto permite "
            "usar usuario y contraseña, tokens, OAuth2 o certificados cuando el servidor "
            "los admita. Las credenciales permanecen cifradas en el perfil local de QGIS; "
            "el plugin sólo guarda el identificador de la configuración.</p>"
            "<p><i>La autenticación no puede reparar servidores caídos ni eludir captchas "
            "o restricciones del proveedor.</i></p>"
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

        title = QLabel(f"<h3>{service_name}</h3>")
        title.setWordWrap(True)
        layout.addWidget(title)

        explanation = QLabel(
            "Seleccione una configuración existente o cree una nueva. QGIS guardará "
            "el usuario, la contraseña, el token o el certificado en la base de "
            "autenticación cifrada del perfil de esta PC. PeruSpatial Hub sólo "
            "conservará el identificador de esa configuración."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        resource = QLabel(f"<b>Ámbito:</b> {service_url}")
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
        note.setStyleSheet("color: #666;")
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
        self.auth_scopes = self.load_auth_scopes()
        self.setWindowTitle("PeruSpatial Hub")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )

        # Set main widget
        self.main_widget = QWidget()
        self.setWidget(self.main_widget)
        
        # Main layout
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(8)

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
        self.splitter.setSizes([350, 250])

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

    def init_header(self):
        """Creates the header title, logo and description."""
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(2, 2, 2, 2)
        header_layout.setSpacing(4)

        # Logo Centered (GisGeo)
        logo_label = QLabel()
        logo_path = os.path.join(self.plugin_dir, "logo.png") if self.plugin_dir else ""
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(logo_label)

        title_label = QLabel("PeruSpatial Hub")
        title_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #0b5394;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_label = QLabel("Catálogo de Geoportales y Servidores del Estado Peruano")
        sub_font = QFont("Segoe UI", 8, QFont.Style.StyleItalic)
        sub_label.setFont(sub_font)
        sub_label.setStyleSheet("color: #555;")
        sub_label.setWordWrap(True)
        sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_layout.addWidget(title_label)
        header_layout.addWidget(sub_label)
        self.main_layout.addWidget(header_widget)

    def init_search_filters(self):
        """Creates search box and category filter combo."""
        self.search_filter_widget = QWidget()
        layout = QHBoxLayout(self.search_filter_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar servicio o capa (ej. sismos, catastro)...")
        self.search_input.setClearButtonEnabled(True)

        self.category_combo = QComboBox()
        self.category_combo.addItem("Todas las Categorías")
        self.category_combo.addItems(CATALOG_CATEGORIES)
        self.category_combo.setFixedWidth(130)

        self.btn_service_status = QToolButton()
        self.btn_service_status.setText("ⓘ")
        self.btn_service_status.setToolTip(
            "Ver el estado de instituciones y servicios investigados"
        )
        self.btn_service_status.setAccessibleName("Información de servicios investigados")
        self.btn_service_status.setFixedSize(30, 30)
        self.btn_service_status.clicked.connect(self.show_service_status_dialog)

        layout.addWidget(self.search_input)
        layout.addWidget(self.category_combo)
        layout.addWidget(self.btn_service_status)

    def init_tree_widget(self):
        """Creates tree widget for service categories and list."""
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Servicio / Institución", "Tipo"])
        self.tree_widget.setHeaderHidden(False)
        self.tree_widget.setColumnWidth(0, 220)
        self.tree_widget.setColumnWidth(1, 100)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #dcdcdc;
                background-color: #ffffff;
            }
            QTreeWidget::item {
                padding: 4px;
            }
        """)

    def init_metadata_panel(self):
        """Creates the text panel to show metadata details."""
        self.metadata_panel = QTextBrowser()
        self.metadata_panel.setOpenExternalLinks(True)
        self.metadata_panel.setPlaceholderText("Seleccione un servicio para ver los detalles, URLs y metadatos.")
        self.metadata_panel.setStyleSheet("""
            QTextBrowser {
                border: 1px solid #dcdcdc;
                background-color: #f9f9f9;
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
            }
        """)

    def init_crs_warning_banner(self):
        """Creates a dedicated banner warning about CRS and Datum accuracy."""
        self.crs_banner = QLabel()
        self.crs_banner.setWordWrap(True)
        self.crs_banner.setStyleSheet("""
            QLabel {
                background-color: #fff2cc;
                border: 1px solid #ffe599;
                color: #7f6000;
                padding: 6px;
                border-radius: 4px;
                font-family: 'Segoe UI';
                font-size: 10.5px;
            }
        """)
        # Default text explaining general rules for Peru spatial
        self.crs_banner.setText(
            "<b>💡 Nota de Precisión (Geofísica/Arqueología):</b><br>"
            "Los levantamientos de precisión requieren el datum correcto. Asegúrese de "
            "configurar su proyecto QGIS en el huso UTM adecuado (ej. <b>WGS84 / UTM 18S</b> - EPSG:32718). "
            "Si usa capas históricas en <b>PSAD56</b>, aplique la transformación a WGS84 para evitar desfases."
        )

    def init_action_buttons(self):
        """Creates action buttons grouped at the bottom."""
        self.button_grid_widget = QWidget()
        grid = QGridLayout(self.button_grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)

        self.btn_add_layer = QPushButton("Añadir al Mapa")
        self.btn_add_layer.setStyleSheet("background-color: #4caf50; color: white; font-weight: bold; padding: 6px;")
        
        self.btn_register_browser = QPushButton("Registrar Conexión")
        self.btn_register_browser.setStyleSheet("padding: 6px;")

        self.btn_register_all = QPushButton("Registrar Todo")
        self.btn_register_all.setStyleSheet("background-color: #0b5394; color: white; padding: 6px;")
        
        self.btn_copy_url = QPushButton("Copiar URL")
        self.btn_copy_url.setStyleSheet("padding: 6px;")

        self.btn_open_browser = QPushButton("Ver en Web")
        self.btn_open_browser.setStyleSheet("padding: 6px;")

        self.btn_about = QPushButton("Acerca de")
        self.btn_about.setStyleSheet("padding: 6px;")

        self.btn_service_access = QPushButton("Configurar acceso privado")
        self.btn_service_access.setStyleSheet(
            "background-color: #674ea7; color: white; font-weight: bold; padding: 6px;"
        )

        self.btn_health_check = QPushButton("Verificar Servidores")
        self.btn_health_check.setStyleSheet(
            "background-color: #e65100; color: white; font-weight: bold; padding: 6px;"
        )
        self.btn_health_check.setToolTip("Verificar la conectividad de todos los servidores del catálogo")

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Cargando...")
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setVisible(False)

        # Grid configuration
        grid.addWidget(self.btn_add_layer, 0, 0)
        grid.addWidget(self.btn_register_browser, 0, 1)
        grid.addWidget(self.btn_copy_url, 1, 0)
        grid.addWidget(self.btn_open_browser, 1, 1)
        grid.addWidget(self.btn_register_all, 2, 0)
        grid.addWidget(self.btn_about, 2, 1)
        grid.addWidget(self.btn_health_check, 3, 0)
        grid.addWidget(self.btn_service_access, 3, 1)
        grid.addWidget(self.progress_bar, 4, 0, 1, 2)

        # Event handlers
        self.btn_add_layer.clicked.connect(self.add_selected_layer)
        self.btn_register_browser.clicked.connect(self.register_selected_connection)
        self.btn_register_all.clicked.connect(self.register_all_connections)
        self.btn_copy_url.clicked.connect(self.copy_selected_url)
        self.btn_open_browser.clicked.connect(self.open_selected_web)
        self.btn_about.clicked.connect(self.show_about_dialog)
        self.btn_service_access.clicked.connect(self.configure_selected_service_access)
        self.btn_health_check.clicked.connect(self.check_all_servers_health)

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
            menu.addAction("📂 Expandir / Colapsar", lambda: item.setExpanded(not item.isExpanded()))
            if data.get("is_loaded", False):
                menu.addAction("🔄 Recargar servidor", lambda: self.refresh_node(item))
            menu.addSeparator()
            if ntype != "arcgis_group":
                menu.addAction("📌 Registrar Conexión", self.register_selected_connection)
            menu.addAction("📋 Copiar URL", self.copy_selected_url)
            menu.addAction("🌐 Ver en Web", self.open_selected_web)
        elif ntype in self.LAYER_TYPES:
            selected = self.tree_widget.selectedItems()
            if len(selected) > 1:
                layer_count = sum(
                    1 for it in selected
                    if (it.data(0, Qt.ItemDataRole.UserRole) or {}).get("type") in self.LAYER_TYPES
                )
                menu.addAction(f"➕ Añadir {layer_count} capas al Mapa", self.add_selected_layer)
            else:
                menu.addAction("➕ Añadir al Mapa", self.add_selected_layer)
            menu.addSeparator()
            menu.addAction("📋 Copiar URL", self.copy_selected_url)
            menu.addAction("🌐 Ver en Web", self.open_selected_web)
            menu.addSeparator()
            if self._is_favorite(data):
                menu.addAction("💔 Quitar de Favoritos", lambda: self.remove_from_favorites(item))
            else:
                menu.addAction("⭐ Añadir a Favoritos", lambda: self.add_to_favorites(item))

        if self.normalize_auth_scope(data.get("service_url") or data.get("url", "")):
            menu.addSeparator()
            menu.addAction("🔐 Configurar acceso privado", self.configure_selected_service_access)

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
            placeholder.setText(0, "Sin favoritos. Use clic derecho → ⭐ para agregar.")
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
        """Test connectivity to every live server and show the results in a dialog."""
        from qgis.PyQt.QtWidgets import QApplication

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self.live_servers))
        self.progress_bar.setValue(0)
        self.btn_health_check.setEnabled(False)
        QApplication.processEvents()

        results = []
        for idx, server in enumerate(self.live_servers):
            self.progress_bar.setFormat(f"Verificando {server['institution']}...")
            self.progress_bar.setValue(idx)
            QApplication.processEvents()
            try:
                if server["stype"] == "arcgis_rest":
                    self.fetch_arcgis_json(server["url"], timeout=8, attempts=1)
                else:
                    self.read_service_https(
                        _wms_capabilities_url(server["url"]),
                        timeout=8,
                        headers={"User-Agent": PLUGIN_USER_AGENT, "Accept": "application/xml,text/xml"},
                        authcfg=self.auth_config_for_url(server["url"]),
                    )
                results.append((server, True, ""))
            except Exception as exc:
                results.append((server, False, str(exc)))

        self.progress_bar.setValue(len(self.live_servers))
        self.progress_bar.setVisible(False)
        self.btn_health_check.setEnabled(True)

        online = sum(1 for _, ok, _ in results if ok)
        offline = len(results) - online

        html_rows = []
        for server, ok, error in results:
            color = "#274e13" if ok else "#a20000"
            icon = "✅" if ok else "❌"
            name = f"{server['institution']} - {server['name']}"
            detail = "" if ok else f"<br><small style='color:#666'>{error[:120]}</small>"
            html_rows.append(f"<tr><td>{icon}</td><td style='color:{color}'>{name}{detail}</td></tr>")

        dialog = QDialog(self)
        dialog.setWindowTitle("Estado de Servidores")
        dialog.setMinimumSize(560, 400)
        layout = QVBoxLayout(dialog)

        summary = QLabel(
            f"<h3>Verificación completada</h3>"
            f"<p><b style='color:#274e13'>{online} en línea</b> · "
            f"<b style='color:#a20000'>{offline} sin respuesta</b></p>"
        )
        layout.addWidget(summary)

        browser = QTextBrowser()
        browser.setHtml(f"<table cellpadding='4'>{''.join(html_rows)}</table>")
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

    def fetch_arcgis_json(self, url, timeout=15, attempts=2):
        """Read ArcGIS REST metadata with one retry for intermittent public servers."""
        request_url = _url_with_json(url)
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
                    authcfg=self.auth_config_for_url(url),
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


    def populate_tree(self):
        """Fills the TreeWidget grouping services by institution and adding live servers."""
        self.tree_widget.clear()

        self.search_results_root = QTreeWidgetItem(self.tree_widget)
        self.search_results_root.setText(0, "🔎 Resultados del inventario local")
        self.search_results_root.setText(1, "Sin conexión")
        self.search_results_root.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.search_results_root.setForeground(0, QColor("#38761d"))
        self.search_results_root.setData(0, Qt.ItemDataRole.UserRole, None)
        self.search_results_root.setHidden(True)
        
        # The old fixed layer URLs contained many retired services. Start from
        # live repository roots and discover their current services/layers.
        explorer_root = QTreeWidgetItem(self.tree_widget)
        explorer_root.setText(0, "🌐 Servidores en Vivo (Explorador Completo)")
        explorer_root.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
        explorer_root.setForeground(0, QColor("#0b5394"))
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
            server_item.setText(1, "Servidor ArcGIS REST" if is_arcgis else "Servidor WMS")
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
        self.favorites_root.setText(0, "⭐ Favoritos")
        self.favorites_root.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.favorites_root.setForeground(0, QColor("#bf8f00"))
        self.favorites_root.setData(0, Qt.ItemDataRole.UserRole, None)
        self.populate_favorites_tree()

        # Start with every repository and folder closed. Remote catalogs are
        # loaded only when the user explicitly expands one of them.
        self.tree_widget.collapseAll()
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
            0, f"🔎 Inventario local: {len(results)} de {total} resultado(s)"
        )
        self.search_results_root.setHidden(False)

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
        if node_data and node_data.get("type") in ["server", "folder", "arcgis_service", "ogc_service"] and not node_data.get("is_loaded", False):
            self.load_dynamic_node(item)

    def load_dynamic_node(self, item):
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        url = node_data["url"]
        stype = node_data["stype"]
        inst = node_data["institution"]
        cat = node_data["category"]

        from qgis.PyQt.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        
        item.takeChildren()
        loading_node = QTreeWidgetItem(item)
        loading_node.setText(0, "Cargando...")
        QApplication.processEvents()
        if self._search_cancelled or not self.isVisible():
            if loading_node.parent() is item:
                item.removeChild(loading_node)
            QApplication.restoreOverrideCursor()
            return

        loaded_ok = False
        try:
            if stype == "arcgis_rest":
                data = self.fetch_arcgis_json(
                    url,
                    timeout=6 if self._discovering_catalog else 15,
                    attempts=1 if self._discovering_catalog else 2,
                )
                    
                # Folders
                for f in data.get("folders", []):
                    folder_name = f
                    furl = _append_rest_path(url, folder_name)

                    f_item = QTreeWidgetItem(item)
                    f_item.setText(0, folder_name)
                    f_item.setText(1, "Carpeta REST")
                    f_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
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
                for s in data.get("services", []):
                    sname = s.get("name")
                    stype_str = s.get("type")
                    if not sname or stype_str not in ("MapServer", "FeatureServer", "ImageServer"):
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

                loaded_ok = True

            elif node_data.get("type") == "arcgis_service":
                data = self.fetch_arcgis_json(
                    url,
                    timeout=6 if self._discovering_catalog else 15,
                    attempts=1 if self._discovering_catalog else 2,
                )
                self.populate_arcgis_service_layers(item, node_data, data)
                loaded_ok = True

            elif stype == "wms":
                capabilities_url = _wms_capabilities_url(url)
                payload = self.read_service_https(
                    capabilities_url,
                    timeout=30,
                    headers={
                        "User-Agent": PLUGIN_USER_AGENT,
                        "Accept": "application/xml,text/xml",
                    },
                    authcfg=self.auth_config_for_url(url),
                )
                self.populate_wms_layers(item, node_data, payload)
                loaded_ok = True

            else:
                raise RuntimeError(f"Tipo REST no compatible: {stype}")

        except Exception as e:
            error_node = QTreeWidgetItem(item)
            error_node.setText(0, f"Error al cargar: {str(e)}")
            error_node.setText(1, "Reintentar al expandir")
            error_node.setForeground(0, QColor("red"))
            
        finally:
            if loading_node.parent() is item:
                item.removeChild(loading_node)
            node_data["is_loaded"] = loaded_ok
            item.setData(0, Qt.ItemDataRole.UserRole, node_data)
            QApplication.restoreOverrideCursor()
            # Keep an active search consistent when a matching folder/service
            # is expanded and its nested layers are loaded on demand.
            if self.search_input.text().strip() and not self._discovering_catalog:
                self.filter_services()

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
                    group_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
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
                tree_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
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
                "<p style='color: #666;'>Seleccione un servicio del catálogo superior para ver su descripción "
                "y realizar operaciones.</p>"
            )
            self.crs_banner.setStyleSheet("""
                QLabel {
                    background-color: #fff2cc;
                    border: 1px solid #ffe599;
                    color: #7f6000;
                    padding: 6px;
                    border-radius: 4px;
                    font-size: 10.5px;
                }
            """)
            self.crs_banner.setText(
                "<b>💡 Nota de Precisión (Geofísica/Arqueología):</b><br>"
                "Los levantamientos de precisión requieren el datum correcto. Asegúrese de "
                "configurar su proyecto QGIS en el huso UTM adecuado (ej. <b>WGS84 / UTM 18S</b> - EPSG:32718). "
                "Si usa capas históricas en <b>PSAD56</b>, aplique la transformación a WGS84 para evitar desfases."
            )
            self.btn_add_layer.setEnabled(False)
            self.btn_add_layer.setText("Añadir al Mapa")
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
                    self.btn_add_layer.setText(f"Añadir {layer_count} Capas")
                    self.btn_add_layer.setEnabled(True)
                else:
                    self.btn_add_layer.setText("Añadir al Mapa")
            else:
                self.btn_add_layer.setText("Añadir al Mapa")
            service_url = s.get("service_url") or s.get("url", "")
            has_auth = bool(self.auth_config_for_url(service_url))
            self.btn_service_access.setEnabled(bool(self.normalize_auth_scope(service_url)))
            self.btn_service_access.setText(
                "Acceso privado configurado" if has_auth else "Configurar acceso privado"
            )
            ntype = s.get("type", "service")
            crs_advisory = ""
            if s.get("crs_warning", False):
                crs_advisory = (
                    "<div style='background-color: #f8cecc; border: 1px solid #b85450; color: #a20000; "
                    "padding: 8px; border-radius: 4px; margin-top: 10px;'>"
                    "<b>⚠️ ADVERTENCIA DE CRS / DATUM:</b><br>"
                    "Este servicio contiene capas históricas o de arqueología que tradicionalmente operan en "
                    "<b>PSAD56</b>. Al integrarlas en un proyecto <b>WGS84 / SIRGAS UTM</b>, asegúrese de aplicar "
                    "la transformación de datum oficial de IGN/MINCUL para evitar desplazamientos de hasta 200 metros."
                    "</div>"
                )
                self.crs_banner.setStyleSheet("""
                    QLabel {
                        background-color: #f8cecc;
                        border: 1px solid #b85450;
                        color: #a20000;
                        padding: 6px;
                        border-radius: 4px;
                        font-size: 10.5px;
                    }
                """)
                self.crs_banner.setText(
                    "<b>⚠️ Advertencia de Precisión:</b> Capas arqueológicas/históricas en PSAD56 detectadas. "
                    "¡No asuma WGS84 automáticamente! Transforme la capa para evitar desfases métricos en su retícula."
                )
            else:
                self.crs_banner.setStyleSheet("""
                    QLabel {
                        background-color: #d5e8d4;
                        border: 1px solid #82b366;
                        color: #274e13;
                        padding: 6px;
                        border-radius: 4px;
                        font-size: 10.5px;
                    }
                """)
                self.crs_banner.setText(
                    "<b>✅ Datum Moderno Compatible:</b> Este servicio opera en WGS84 / SIRGAS UTM de forma nativa. "
                    "Se alinea perfectamente con mapas base de satélite y coordenadas de GPS modernas."
                )

            tags_html = "".join([f"<span style='background-color: #e1e1e1; padding: 2px 6px; margin-right: 4px; border-radius: 3px; font-size: 10px;'>{tag}</span>" for tag in s.get("tags", [])])

            if ntype == "ogc_service":
                html = f"""
                    <h3>{s['name']}</h3>
                    <p><b>Institución:</b> {s['institution']}</p>
                    <p><b>Categoría:</b> {s['category']}</p>
                    <p><b>Tipo:</b> Servicio WMS oficial verificado</p>
                    <p><b>Descripción:</b> Expanda este nodo para consultar el catálogo WMS y añadir cualquiera de sus capas directamente al mapa.</p>
                    <p><b>URL del Servidor:</b><br><a href='{s['url']}'>{s['url']}</a></p>
                """
                self.metadata_panel.setHtml(html)
                self.btn_add_layer.setEnabled(False)
                self.btn_register_browser.setEnabled(True)
                self.btn_copy_url.setEnabled(True)
                self.btn_open_browser.setEnabled(True)
            elif ntype in ["server", "folder", "arcgis_service", "arcgis_group", "wms_group"]:
                html = f"""
                    <h3>{s['name']}</h3>
                    <p><b>Institución:</b> {s['institution']}</p>
                    <p><b>Categoría:</b> {s['category']}</p>
                    <p><b>Tipo:</b> Directorio de Servidor ({s['stype']})</p>
                    <p><b>Descripción:</b> Directorio en vivo del servidor del estado peruano. Expanda este nodo en el catálogo superior para explorar dinámicamente todas sus subcarpetas y servicios publicados en tiempo real.</p>
                    <p><b>URL del Servidor:</b><br><a href='{s['url']}'>{s['url']}</a></p>
                """
                self.metadata_panel.setHtml(html)
                self.btn_add_layer.setEnabled(False)
                self.btn_register_browser.setEnabled(ntype != "arcgis_group")
                self.btn_copy_url.setEnabled(True)
                self.btn_open_browser.setEnabled(True)
            else:
                friendly_t = self.friendly_type(s['stype'])
                html = f"""
                    <h3>{s['name']}</h3>
                    <p><b>Institución:</b> {s['institution']}</p>
                    <p><b>Categoría:</b> {s['category']}</p>
                    <p><b>Tipo de Conexión:</b> {friendly_t}</p>
                    <p><b>Descripción:</b> {s.get('description', '')}</p>
                    <p><b>URL del Servicio:</b><br><a href='{s['url']}'>{s['url']}</a></p>
                    <p><b>Etiquetas:</b> {tags_html}</p>
                    {crs_advisory}
                """
                self.metadata_panel.setHtml(html)
                self.btn_add_layer.setEnabled(True)
                self.btn_register_browser.setEnabled(True)
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
            clipboard = self.iface.mainWindow().clipboard()
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
