"""WMS protocol parsing shared by the QGIS panel and offline inventory builder."""

from __future__ import annotations

import xml.etree.ElementTree as ET

MAX_WMS_BYTES = 25 * 1024 * 1024


def merge_crs(inherited, own):
    """WMS child layers inherit and extend their parent's coordinate systems."""
    return list(dict.fromkeys([*inherited, *own]))


def parse_wms_layer_catalog(payload):
    """Read a WMS 1.1/1.3 catalogue without Qt string binding assumptions.

    ElementTree does not fetch external DTDs. Ordinary WMS 1.1 DOCTYPE
    declarations are accepted, while entity declarations are rejected.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_WMS_BYTES:
        raise ValueError("GetCapabilities WMS excede el límite permitido")
    if b"<!ENTITY" in payload.replace(b"\x00", b"").upper():
        raise ValueError("GetCapabilities WMS contiene entidades XML no permitidas")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"GetCapabilities WMS no devolvió XML válido: {exc}") from exc

    def local_name(node):
        return node.tag.rsplit("}", 1)[-1]

    if local_name(root) not in {"WMS_Capabilities", "WMT_MS_Capabilities"}:
        raise ValueError("La respuesta no es un documento GetCapabilities WMS")
    capability = next((node for node in root if local_name(node) == "Capability"), None)
    root_layer = next((node for node in capability if local_name(node) == "Layer"), None) if capability is not None else None
    if root_layer is None:
        raise ValueError("GetCapabilities WMS no contiene un catálogo de capas")

    def read_layer(node, depth=0):
        if depth > 100:
            raise ValueError("El catálogo WMS excede la profundidad permitida")
        result = {"name": "", "title": "", "crs": [], "children": []}
        for child in node:
            name = local_name(child)
            value = (child.text or "").strip()
            if name in {"Name", "Title"}:
                result[name.lower()] = value
            elif name in {"CRS", "SRS"}:
                result["crs"].extend(value.split())
            elif name == "Layer":
                result["children"].append(read_layer(child, depth + 1))
        result["crs"] = list(dict.fromkeys(result["crs"]))
        return result

    result = read_layer(root_layer)
    queue = [result]
    named_layers = 0
    while queue:
        layer = queue.pop()
        named_layers += bool(layer["name"])
        queue.extend(layer["children"])
    if not named_layers:
        raise ValueError("El servidor WMS no publicó capas con nombre")
    return result
