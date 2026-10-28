"""WMS protocol parsing shared by the QGIS panel and offline inventory builder."""

from __future__ import annotations

from xml.parsers import expat

MAX_WMS_BYTES = 25 * 1024 * 1024
MAX_XML_DEPTH = 128
MAX_XML_ELEMENTS = 100_000
MAX_WMS_LAYERS = 20_000
MAX_FIELD_CHARS = 1_000_000


def merge_crs(inherited, own):
    """WMS child layers inherit and extend their parent's coordinate systems."""
    return list(dict.fromkeys([*inherited, *own]))


def parse_wms_layer_catalog(payload):
    """Stream WMS XML with entities disabled and explicit resource limits.

    External DTD identifiers in WMS 1.1 are accepted but never resolved.
    Internal DTD subsets, declarations and external entities are rejected
    by parser callbacks before entity expansion. Only catalogue fields are
    retained, rather than a complete untrusted XML tree.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_WMS_BYTES:
        raise ValueError("GetCapabilities WMS excede el límite permitido")
    parser = expat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    element_stack = []
    layer_stack = []
    result = None
    capture = None
    element_count = 0
    layer_count = 0

    def reject_entities(*_args):
        raise ValueError("GetCapabilities WMS contiene entidades XML no permitidas")

    def doctype(_name, _system_id, _public_id, internal_subset):
        if internal_subset:
            reject_entities()

    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = reject_entities
    parser.UnparsedEntityDeclHandler = reject_entities
    parser.ExternalEntityRefHandler = reject_entities

    def start(name, _attributes):
        nonlocal element_count, layer_count, result, capture
        name = name.rsplit("}", 1)[-1]
        if not element_stack and name not in {"WMS_Capabilities", "WMT_MS_Capabilities"}:
            raise ValueError("La respuesta no es un documento GetCapabilities WMS")
        element_count += 1
        if element_count > MAX_XML_ELEMENTS or len(element_stack) >= MAX_XML_DEPTH:
            raise ValueError("GetCapabilities WMS excede el límite de elementos o profundidad")
        parent = element_stack[-1] if element_stack else None
        element_stack.append(name)
        if name == "Layer" and (parent == "Capability" or (parent == "Layer" and layer_stack)):
            layer_count += 1
            if layer_count > MAX_WMS_LAYERS:
                raise ValueError("GetCapabilities WMS excede el límite de capas")
            layer = {"name": "", "title": "", "crs": [], "children": []}
            if layer_stack:
                layer_stack[-1][0]["children"].append(layer)
            elif result is None:
                result = layer
            else:
                raise ValueError("GetCapabilities WMS contiene varias capas raíz")
            layer_stack.append((layer, len(element_stack)))
        elif (layer_stack and len(element_stack) == layer_stack[-1][1] + 1
              and name in {"Name", "Title", "CRS", "SRS"}):
            capture = {"field": name, "depth": len(element_stack), "parts": [], "chars": 0}

    def text(value):
        if capture is not None:
            capture["chars"] += len(value)
            if capture["chars"] > MAX_FIELD_CHARS:
                raise ValueError("GetCapabilities WMS excede el límite de texto por campo")
            capture["parts"].append(value)

    def end(_name):
        nonlocal capture
        depth = len(element_stack)
        if capture is not None and capture["depth"] == depth:
            value = "".join(capture["parts"]).strip()
            layer = layer_stack[-1][0]
            if capture["field"] in {"Name", "Title"}:
                layer[capture["field"].lower()] = value
            else:
                layer["crs"] = list(dict.fromkeys([*layer["crs"], *value.split()]))
            capture = None
        if layer_stack and layer_stack[-1][1] == depth:
            layer_stack.pop()
        element_stack.pop()

    parser.StartElementHandler = start
    parser.CharacterDataHandler = text
    parser.EndElementHandler = end
    try:
        parser.Parse(payload, True)
    except expat.ExpatError as exc:
        raise ValueError(f"GetCapabilities WMS no devolvió XML válido: {exc}") from exc
    if result is None:
        raise ValueError("GetCapabilities WMS no contiene un catálogo de capas")
    queue = [result]
    named_layers = 0
    while queue:
        layer = queue.pop()
        named_layers += bool(layer["name"])
        queue.extend(layer["children"])
    if not named_layers:
        raise ValueError("El servidor WMS no publicó capas con nombre")
    return result
