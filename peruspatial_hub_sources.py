"""Official catalog sources bundled with PeruSpatial Hub."""

from urllib.parse import urlsplit, urlunsplit


def _endpoint(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))

CATALOG_CATEGORIES = (
    "Arqueología y Cultura",
    "Agricultura y Catastro",
    "Clima y Riesgos",
    "Geología y Minería",
    "Hidrología y Agua",
    "Límites y Cartografía",
    "Medio Ambiente",
    "Transporte e Infraestructura",
)


LIVE_SERVERS = (
    {
        "institution": "SENACE",
        "name": "Certificaciones Ambientales - Interoperabilidad (REST)",
        "url": "https://geosenace.senace.gob.pe/arcgis/rest/services/INTEROPERABILIDAD",
        "stype": "arcgis_rest",
        "category": "Medio Ambiente",
    },
    {
        "institution": "SENACE",
        "name": "Áreas de Influencia - GeoSENACE (REST)",
        "url": "https://geosenace.senace.gob.pe/arcgis/rest/services/GEOSENACE",
        "stype": "arcgis_rest",
        "category": "Medio Ambiente",
    },
    {
        "institution": "SENAMHI",
        "name": "Clasificación Climática (WMS)",
        "url": "https://idesep.senamhi.gob.pe/geoserver/g_05_01/wms",
        "stype": "wms",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "SENAMHI",
        "name": "Precipitación (WMS)",
        "url": "https://idesep.senamhi.gob.pe/geoserver/g_05_02/wms",
        "stype": "wms",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "SENAMHI",
        "name": "Sectores Climáticos (WMS)",
        "url": "https://idesep.senamhi.gob.pe/geoserver/g_00_02/wms",
        "stype": "wms",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "SENAMHI",
        "name": "Cambio de Precipitación 2050 (WMS)",
        "url": "https://idesep.senamhi.gob.pe/geoserver/g_06_13/wms",
        "stype": "wms",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "SENAMHI",
        "name": "Erosión del Suelo (WMS)",
        "url": "https://idesep.senamhi.gob.pe/geoserver/g_08_03/wms",
        "stype": "wms",
        "category": "Medio Ambiente",
    },
    {
        "institution": "SENAMHI",
        "name": "Zonas de Vida (WMS)",
        "url": "https://idesep.senamhi.gob.pe/geoserver/g_05_06/wms",
        "stype": "wms",
        "category": "Medio Ambiente",
    },
    {
        "institution": "SENAMHI",
        "name": "Vigilancia de Incendios (WMS)",
        "url": "https://idesep.senamhi.gob.pe/geoserver/g_09_03/wms",
        "stype": "wms",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "ANA (SNIRH)",
        "name": "Recursos Hídricos - Directorio SNIRH (REST)",
        "url": "https://geosnirh.ana.gob.pe/server/rest/services",
        "stype": "arcgis_rest",
        "category": "Hidrología y Agua",
    },
    {
        "institution": "CENEPRED (SIGRID)",
        "name": "SIGRID Riesgos y Desastres (REST)",
        "url": "https://sigrid.cenepred.gob.pe/arcgis/rest/services",
        "stype": "arcgis_rest",
        "category": "Clima y Riesgos",
    },
    {
        "institution": "MTC (Provías Nacional)",
        "name": "Infraestructura y Red Vial Nacional (REST)",
        "url": "https://giserver.proviasnac.gob.pe/arcgis/rest/services",
        "stype": "arcgis_rest",
        "category": "Transporte e Infraestructura",
    },
    {
        "institution": "MIDAGRI",
        "name": "Catastro Rural - Servicios Interoperables (REST)",
        "url": "https://winlmprap09.midagri.gob.pe/winlmprap13/rest/services/ogc",
        "stype": "arcgis_rest",
        "category": "Agricultura y Catastro",
    },
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

# Derived from the same definitions used by the tree and inventory builder.
ACTIVE_REST_ROOTS = frozenset(_endpoint(source["url"]) for source in LIVE_SERVERS
                              if source["stype"] == "arcgis_rest")
ACTIVE_WMS_ROOTS = frozenset(_endpoint(source["url"]) for source in LIVE_SERVERS
                             if source["stype"] == "wms")
