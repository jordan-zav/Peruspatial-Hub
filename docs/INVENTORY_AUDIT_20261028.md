# Auditoría de servicios y metadatos internos

Fecha de la instantánea: 28 de octubre de 2026, desde las 20:02 UTC.
Alcance: las 27 fuentes configuradas y todas las entradas del catálogo existente.
Se consultaron metadatos públicos, sin desactivar TLS ni intentar acceder a
ramas protegidas mediante credenciales ajenas.

## Cobertura

| Revisión | Resultado |
| --- | --- |
| Inventario anterior | 12.396 entradas |
| Inventario corregido | 12.393 entradas |
| Servicios REST contrastados | 1.881 |
| Servicios REST con metadatos accesibles | 1.863 |
| Servicios REST no verificables | 18 |
| ImageServer examinados, incluidos en los servicios anteriores | 10 |
| Registros de capas, tablas y grupos con metadatos | 11.242 |
| Capas WMS nombradas contrastadas con GetCapabilities | 464 |
| Esquemas de atributos examinados | Más de 218.000 descriptores de campos publicados |

Las 18 respuestas fallidas fueron nueve solicitudes de token, tres respuestas
de servicio no encontrado, cuatro respuestas de servicio detenido o no
configurado y dos tiempos de espera. También hubo carpetas protegidas durante
la enumeración de directorios. Por ello seis fuentes quedaron como parciales;
no se afirma haber enumerado el contenido que esas ramas ocultan.

## Errores concretos corregidos

Tres IDs estaban indexados como capas aunque los metadatos actuales los
identifican como grupos:

| Servicio | ID | Corrección |
| --- | --- | --- |
| SERFOR, Visor/ZF_HUA_TEM/MapServer | 6 | Ahora es el grupo Temáticos de ZF. Capacidad de Uso Mayor corresponde al ID 9 |
| Provías, MTC__InfraestructuraVial/MapServer | 0 | Es el grupo INFRAESTRUCTURA VIAL |
| Provías, PROVIAS/MTC_InfraestructuraVial/MapServer | 0 | Es el grupo INFRAESTRUCTURA VIAL |

Se retiraron del índice de capas individuales esas tres entradas. Los servicios
y sus grupos siguen disponibles para exploración. No se eliminó una fuente
por un fallo temporal ni se trataron como retiradas las capas inaccesibles.

La retención anterior operaba sobre toda la fuente: un error en otra carpeta
podía conservar una capa obsoleta de un servicio que sí respondió. Ahora se
registra la cobertura por servicio y se actualiza el inventario confirmado de
ese servicio. Durante una pasada parcial, la simple ausencia de un servicio
en un directorio público no demuestra que haya desaparecido: podría estar
protegido. Esas entradas se conservan como sin verificar.

Se añadió además una defensa durante la carga: un favorito o resultado antiguo
que apunte a un ID convertido en grupo devuelve un mensaje para explorar el
servicio, en lugar de cargarlo silenciosamente con el nombre antiguo.

## Metadatos que ahora conserva el catálogo

La clasificación usa el tipo publicado además de la geometría. Las tablas
aparecen como tablas, los grupos no se presentan como hojas importables y un
Feature Layer no se confunde con ráster porque su resumen omita geometryType.
MapServer mantiene la posibilidad de usar su representación ráster cuando el
proveedor vectorial no sea compatible.

La actualización corrigió 9.116 etiquetas de tipo y completó 4.763 rutas de
grupos. Hay 9.799 entradas con número de campos, 9.363 con tipo de geometría y
11.576 con referencia espacial publicada. Estos recuentos incluyen los tipos
de recurso a los que cada propiedad resulta aplicable. Una tabla sin geometría
no hereda una extensión o CRS espacial del servicio.

metadata_level distingue la enumeración del directorio de los metadatos de
servicio y capa. Cada entrada recién verificada conserva su fecha; una entrada
retenida no recibe como fecha de verificación la de una actualización ajena.
Una reconstrucción desde respuestas guardadas mantiene la fecha de la
instantánea, en lugar de presentarse como una consulta de red nueva.

Las respuestas que contienen un JSON válido pero no un inventario ArcGIS se
rechazan antes de reemplazar entradas. Se comprueban IDs duplicados, ciclos
de grupos, listas de capas y tablas, y metadatos reales de ImageServer.
Cuando el recurso colectivo de metadatos no está disponible se consultan las
capas individualmente. Se conservaron 58 entradas como sin verificar.

## Esquemas y CRS de las fuentes

Se encontraron 61 capas con nombres de campos repetidos en sus metadatos
oficiales. Se conserva el esquema original en la evidencia y se muestra una
advertencia en los detalles del catálogo; no se inventan nombres para ocultar
el problema.

Una comprobación nativa de QGIS con Caminos prehispánicos de MINCUL confirmó
53 campos declarados y 51 expuestos por el proveedor. La tabla
DASH_ESTACIONES_RIMAC_DATOS_2026 de ANA cargó con sus cinco campos y sin
geometría. Estas dos comprobaciones no equivalen a descargar y validar todos
los valores de atributos de todas las capas.

Las 53 definiciones espaciales REST distintas se resolvieron en QGIS 3.44
mediante EPSG, ESRI o el WKT publicado. Se añadieron avisos de datum a cinco
entradas de SERFOR declaradas en PSAD56: el servicio y sus cuatro subcapas.
El respaldo WKT solo recupera un CRS ausente; no sustituye un CRS válido del
proveedor ni transforma o reetiqueta coordenadas para hacer coincidir un mapa.

Los WMS anuncian en conjunto 6.780 opciones de CRS; QGIS 3.44 no reconoce 348
de ellas. Son opciones de reproyección anunciadas por los servidores, no 348
capas inválidas ni una declaración del datum original de cada capa. Las 464
capas nombradas ofrecen un CRS compatible; todas anuncian EPSG:4326 o
EPSG:3857. Se conserva la declaración original y el cargador prioriza el CRS
del proyecto cuando está anunciado, seguido de esas opciones habituales.

## Comprobación y evidencia

Las pruebas cubren respuestas incompletas, retención selectiva, cambios de tipo
de ID, tablas, tipos sin geometría en el resumen, rutas de grupos, fechas,
avisos PSAD56 y respaldo WKT. Las pruebas de widgets accionan los controles
reales de Qt/QGIS y verifican también el mensaje de un ID obsoleto.

La auditoría genera los siguientes archivos fuera del código distribuido:

- layer-metadata.csv: inventario de metadatos de capas, grupos, tablas y WMS.
- field-schemas.csv: nombres, tipos y alias de los campos publicados, conservando los duplicados como evidencia.
- comparison.json: entradas retiradas, IDs convertidos en grupos y cambios de metadatos.
- summary.json: cobertura, respuestas no verificables y advertencias.
- Respuestas originales identificadas por el hash de su URL, para repetir el análisis sin nuevas peticiones.
- qgis-inventory.json: resolución de CRS y comprobaciones nativas de esquemas.

No se validaron todas las geometrías, valores de atributos ni renderizados de
las más de doce mil entradas. Los servicios externos pueden cambiar después
de la instantánea; un esquema consistente no certifica la calidad geológica
o posicional del dataset.

Referencias de protocolo:
[metadatos colectivos de capas y tablas](https://developers.arcgis.com/rest/services-reference/enterprise/all-layers-and-tables/)
y [metadatos de una capa o tabla](https://developers.arcgis.com/rest/services-reference/enterprise/layer-table/).
