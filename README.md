# PeruSpatial Hub

<p align="center">
  <a href="https://github.com/jordan-zav/Peruspatial-Hub/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/jordan-zav/Peruspatial-Hub?style=flat-square"></a>
  <a href="https://github.com/jordan-zav/Peruspatial-Hub/actions/workflows/tests.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/jordan-zav/Peruspatial-Hub/tests.yml?branch=main&label=tests&style=flat-square"></a>
  <img alt="QGIS 3.34+" src="https://img.shields.io/badge/QGIS-3.34%2B-589632?style=flat-square&logo=qgis&logoColor=white">
  <a href="LICENSE"><img alt="GNU GPLv3" src="https://img.shields.io/badge/License-GPLv3-blue?style=flat-square"></a>
</p>

Versión estable: 1.3.0

**PeruSpatial Hub** es un plugin para QGIS diseñado para centralizar y facilitar el acceso a la Infraestructura de Datos Espaciales (IDE) de las principales instituciones públicas del Perú. 

Este plugin es una herramienta indispensable para profesionales en **geología, geografía, teledetección, ingeniería ambiental, logística administrativa, hidrocarburos e hidrogeología**, ya que permite explorar e integrar de forma inmediata la cartografía base y temática del país.

## Búsqueda local instantánea

El plugin incluye un inventario de más de 8,000 servicios y capas oficiales. Escribir en el buscador filtra únicamente ese archivo local, con un breve debounce y un máximo de 200 resultados visibles. **La búsqueda no realiza solicitudes HTTP** y no depende de la velocidad de los geoportales.

Las consultas en vivo ocurren solamente cuando el usuario expande explícitamente un servidor o servicio, o cuando añade una capa al mapa. El inventario puede regenerarse fuera de QGIS con:

```bash
python scripts/build_catalog.py
```

Los servidores con errores de certificado, autenticación o disponibilidad permanecen accesibles desde el explorador en vivo, pero nunca bloquean el cuadro de búsqueda.

## Descarga

Descarga el ZIP instalable desde la [última release](https://github.com/jordan-zav/Peruspatial-Hub/releases/latest) y cárgalo mediante **Complementos → Administrar e instalar complementos → Instalar a partir de ZIP**.

## Licencia de código abierto

PeruSpatial Hub se distribuye bajo la GNU General Public License v3.0. Puede usar, estudiar, modificar y redistribuir el código de acuerdo con los términos incluidos en el archivo LICENSE.

---

## 🚀 Características Principales

1. **Catálogo Unificado**: Directorios GIS oficiales verificados y clasificados por institución y temática. Cada directorio descubre dinámicamente los servicios que la institución publica en ese momento.
2. **Buscador Inteligente**: Filtra en tiempo real por palabras clave (ej: "sismos", "concesiones", "cuencas") y por categoría.
3. **Carga de Capas REST**: Expande un servicio ArcGIS y haz doble clic en una subcapa para cargarla mediante el proveedor raster o vectorial correspondiente. Las conexiones WMS se registran en el panel Explorador de QGIS para seleccionar allí sus capas publicadas.
4. **Integración con el Explorador de QGIS**: Registra de forma individual o masiva todas las conexiones oficiales del catálogo directamente en el panel **Explorador** nativo de QGIS (bajo las categorías WMS/WMTS y ArcGIS REST).
5. **Asistente de Precisión de CRS / Datum**: Panel de advertencia dinámico que le guiará para evitar errores al trabajar con datums mixtos (especialmente la transformación del datum histórico **PSAD56** al moderno **WGS84 / SIRGAS UTM**), garantizando la precisión métrica obligatoria en trabajos arqueológicos y geofísicos.
6. **Estado Transparente de Fuentes**: El botón de información junto al buscador explica qué instituciones fueron investigadas, cuáles presentan fallas técnicas y cuáles requieren identificación. También documenta la exploración futura de accesos autenticados mediante mecanismos oficiales y seguros.
---

## 📂 Servidores de información integrados y verificados

La disponibilidad indicada fue comprobada el 15 de julio de 2026. Como son servicios externos administrados por cada institución, pueden cambiar o quedar temporalmente fuera de línea sin previo aviso.

*   **INGEMMET (GEOCATMIN)**: dos directorios ArcGIS REST activos con catastro minero, geología, geoquímica y otros servicios publicados por la institución.
*   **IGN e IDEP**: cartografía nacional y directorios institucionales publicados mediante ArcGIS REST.
*   **ANA mediante IDEP**: servicio institucional con humedales costeros, manantiales, glaciares, estaciones hidrometeorológicas y unidades hidrográficas.
*   **IGP**: directorio ArcGIS REST oficial, catálogo WMS general y accesos WMS directos a Condición NDVI y Anomalías NDVI de los últimos 30 días. Incluye las capas empleadas por Zonifica Perú, estaciones isotópicas, monitoreo sísmico y volcánico, mapas base y otras colecciones públicas. Tanto las capas REST como las WMS pueden explorarse y añadirse directamente al mapa.
*   **MINAM**: directorio ArcGIS REST del Geoservidor MINAM, con servicios ambientales y de zonificación publicados actualmente.
*   **SERNANP**: directorio ArcGIS REST con gestión, monitoreo y cartografía de áreas naturales protegidas.
*   **SERFOR**: nuevo directorio oficial de GeoSERFOR con servicios forestales, imágenes, geoprocesamiento y visor.
*   **Ministerio de Cultura**: directorio oficial SIGDA con los servicios que la institución mantiene publicados.
*   **OSINERGMIN**: Mapa Energético Minero con servicios de electricidad, gas natural, hidrocarburos, minería y cartografía.
*   **OEFA**: directorio PIFA con servicios públicos de monitoreo, fiscalización, emergencias ambientales, vigilancia y datos interoperables.

### Fuentes no integradas actualmente

*   **CENEPRED**: el visor SIGRID ofrece acceso mediante cuenta o correo, pero su ArcGIS Web Adaptor indicó que no podía acceder a ningún servidor interno durante la verificación. No se trata simplemente de una solicitud de login REST.
*   **COFOPRI**: el dominio histórico responde con una cadena de certificado incompleta y el endpoint REST devuelve 404. No se integrará desactivando la validación TLS.
*   **SUNARP**: el Visor BGR requiere DNI vigente, fecha de emisión y captcha. No existe un directorio REST anónimo verificado que el plugin pueda registrar responsablemente.

El botón de información de la interfaz mantiene este diagnóstico visible dentro de QGIS. El plugin no incluye credenciales, no elude captchas y no desactiva la validación de certificados.

---

## 🛠️ Instalación Manual

Dado que el plugin está en desarrollo activo, puede instalarlo manualmente siguiendo estos pasos:

1. Localice la carpeta de plugins de su perfil de QGIS. Normalmente se encuentra en:
   * **Windows**: C:\Users\TuUsuario\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\
   * **Linux**: ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
   * **macOS**: /Users/TuUsuario/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
2. Copie la carpeta completa peruspatial_hub dentro del directorio plugins anterior.
3. Abra QGIS, vaya al menú superior **Complementos** > **Administrar e instalar complementos...**
4. Busque **PeruSpatial Hub** en la sección "Instalados" y active la casilla correspondiente.
5. Verá un nuevo ícono de globo/base de datos en la barra de herramientas "Base de datos" y una opción en el menú **Base de datos** > **PeruSpatial Hub** para abrir el panel.

---

## ⚠️ Reglas Críticas de Precisión Espacial (Datum y CRS)

Si está trabajando con datos arqueológicos o geofísicos en el Perú, siga rigurosamente estas reglas:

*   **No asuma WGS84 como único datum**: Las capas antiguas y planos arqueológicos heredados suelen estar en **PSAD56 (Provisional South American 1956)**. Si simplemente "define" la proyección como WGS84, sufrirá un **desfase de hasta 200 metros** en el terreno.
*   **Use transformaciones de datum oficiales**: Al importar datos de instituciones como el Ministerio de Cultura en PSAD56, aplique siempre herramientas de reproyección utilizando los coeficientes oficiales de transformación hacia WGS84/SIRGAS.
*   **Mantenga un CRS Maestro de Proyecto**: Realice el procesamiento geofísico y mapeo en un único CRS proyectado (generalmente UTM Huso 17S, 18S o 19S dependiendo de la ubicación regional en el Perú).

## Soporte y código fuente

Desarrollado por [Jordan Zavaleta](https://gisgeo.dev).

El código fuente y el seguimiento de incidencias se encuentran en [GitHub](https://github.com/jordan-zav/peruspatial-hub).

## Desarrollo

Las funciones de construcción de URLs se prueban sin depender de una instalación de QGIS:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
python scripts/package_plugin.py
```

El empaquetador crea un ZIP con la carpeta `peruspatial_hub` requerida por QGIS.
