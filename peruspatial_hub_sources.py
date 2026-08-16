"""Official catalog sources bundled with PeruSpatial Hub."""

CATALOG_CATEGORIES = (
    "Arqueología y Cultura",
    "Clima y Riesgos",
    "Geología y Minería",
    "Hidrología y Agua",
    "Límites y Cartografía",
    "Medio Ambiente",
)

ACTIVE_REST_ROOTS = {
    "https://ide.igp.gob.pe/arcgis/rest/services",
    "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services",
    "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/WGS84_18",
    "https://www.idep.gob.pe/geoportal/rest/services/SERVICIOS_IGN",
    "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES",
    "https://geoservicios.sernanp.gob.pe/arcgis/rest/services",
    "https://geoservidorperu.minam.gob.pe/arcgis/rest/services",
    "https://geo.serfor.gob.pe/geoservicios/rest/services",
    "https://sigda.cultura.gob.pe/sigda/rest/services",
    "https://gisem.osinergmin.gob.pe/serverosih/rest/services",
    "https://pifa.oefa.gob.pe/arcgis/rest/services",
}

ACTIVE_WMS_ROOTS = {
    "https://ide.igp.gob.pe/geoserver/ows",
    "https://ide.igp.gob.pe/geoserver/SCAH_NDVI/wms",
    "https://ide.igp.gob.pe/geoserver/SCAHanomNDVI/wms",
}

LIVE_SERVERS = (
    {
        "institution": "INGEMMET (GEOCATMIN)",
        "name": "Servicios REST Generales (WGS84)",
        "url": "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services",
        "stype": "arcgis_rest",
        "category": "Geología y Minería",
    },
    {
        "institution": "INGEMMET (GEOCATMIN)",
        "name": "Servicios REST Huso 18S (WGS84)",
        "url": "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/WGS84_18",
        "stype": "arcgis_rest",
        "category": "Geología y Minería",
    },
    {
        "institution": "IGN",
        "name": "IGN Servicios de Cartografía (REST)",
        "url": "https://www.idep.gob.pe/geoportal/rest/services/SERVICIOS_IGN",
        "stype": "arcgis_rest",
        "category": "Límites y Cartografía",
    },
    {
        "institution": "IDEP (ANA y otras instituciones)",
        "name": "Servicios Institucionales Oficiales (REST)",
        "url": "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES",
        "stype": "arcgis_rest",
        "category": "Hidrología y Agua",
    },
    {
        "institution": "MINCUL",
        "name": "MINCUL Patrimonio y Arqueología (REST)",
        "url": "https://sigda.cultura.gob.pe/sigda/rest/services",
        "stype": "arcgis_rest",
        "category": "Arqueología y Cultura",
        "crs_warning": True,
    },
    {
        "institution": "SERNANP",
        "name": "SERNANP Áreas Protegidas (REST)",
        "url": "https://geoservicios.sernanp.gob.pe/arcgis/rest/services",
        "stype": "arcgis_rest",
        "category": "Medio Ambiente",
    },
    {
        "institution": "SERFOR",
        "name": "SERFOR Catastro Forestal (REST)",
        "url": "https://geo.serfor.gob.pe/geoservicios/rest/services",
        "stype": "arcgis_rest",
        "category": "Medio Ambiente",
    },
    {
        "institution": "MINAM",
        "name": "MINAM Geoservidor (REST)",
        "url": "https://geoservidorperu.minam.gob.pe/arcgis/rest/services",
        "stype": "arcgis_rest",
        "category": "Medio Ambiente",
    },
    {
        "institution": "OSINERGMIN",
        "name": "OSINERGMIN Energía (REST)",
        "url": "https://gisem.osinergmin.gob.pe/serverosih/rest/services",
        "stype": "arcgis_rest",
        "category": "Límites y Cartografía",
    },
    {
        "institution": "OEFA",
        "name": "PIFA Monitoreo y Fiscalización Ambiental (REST)",
        "url": "https://pifa.oefa.gob.pe/arcgis/rest/services",
        "stype": "arcgis_rest",
        "category": "Medio Ambiente",
    },
    {
        "institution": "IGP",
        "name": "IGP Directorio Geoespacial (REST)",
        "url": "https://ide.igp.gob.pe/arcgis/rest/services",
        "stype": "arcgis_rest",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "IGP",
        "name": "IGP Catálogo General (WMS)",
        "url": "https://ide.igp.gob.pe/geoserver/ows?service=wms",
        "stype": "wms",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "IGP",
        "name": "IGP Condición NDVI - últimos 30 días (WMS)",
        "url": "https://ide.igp.gob.pe/geoserver/SCAH_NDVI/wms?service=wms",
        "stype": "wms",
        "category": "Medio Ambiente",
    },
    {
        "institution": "IGP",
        "name": "IGP Anomalías NDVI - últimos 30 días (WMS)",
        "url": "https://ide.igp.gob.pe/geoserver/SCAHanomNDVI/wms?service=wms",
        "stype": "wms",
        "category": "Medio Ambiente",
    },
)
