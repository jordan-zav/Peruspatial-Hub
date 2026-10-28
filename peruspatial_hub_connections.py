"""Native QGIS settings paths and non-destructive connection registration."""

from urllib.parse import urlsplit


def connection_root(stype):
    """Use the settings tree used by QGIS 3.30+ (minimum supported: 3.34)."""
    if stype == "wms":
        return "connections/ows/items/wms/connections/items"
    if stype in {"arcgis_rest", "arcgis_mapserver", "arcgisfeatureserver", "arcgis_imageserver",
                 "arcgis_map_layer", "arcgis_raster_layer", "arcgis_vector_layer"}:
        return "connections/arcgisfeatureserver/items"
    raise ValueError(f"Tipo de conexión no compatible: {stype}")


def safe_connection_name(name):
    value = "".join(" " if char in "/\\" or ord(char) < 32 or ord(char) == 127 else char
                    for char in str(name or ""))
    return " ".join(value.split()) or "PeruSpatial Hub"


def register_connection(settings, name, url, stype, authcfg="", anonymous_override=False):
    """Preserve other URLs and saved authentication; return the actual saved name."""
    parts = urlsplit(url)
    if parts.scheme.casefold() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Use una URL HTTPS sin credenciales; configure el acceso privado en QGIS")
    root = connection_root(stype)
    base_name = safe_connection_name(name)
    settings.beginGroup(root)
    try:
        # QSettings keys are case-insensitive on Windows. Preserve the stored
        # spelling and reserve names conservatively on every supported platform.
        names = {existing.casefold(): existing for existing in settings.childGroups()}
    finally:
        settings.endGroup()
    candidate = base_name
    for suffix in range(1000):
        candidate = names.get(candidate.casefold(), candidate)
        key = f"{root}/{candidate}/"
        previous_url = settings.value(key + "url", "")
        if candidate.casefold() not in names or previous_url == url:
            break
        candidate = f"{base_name} (PeruSpatial Hub{f' {suffix + 1}' if suffix else ''})"
    else:
        raise ValueError("No se encontró un nombre libre para esta conexión")
    settings.setValue(key + "url", url)
    if authcfg or anonymous_override or not settings.contains(key + "authcfg"):
        settings.setValue(key + "authcfg", authcfg or "")
    return candidate
