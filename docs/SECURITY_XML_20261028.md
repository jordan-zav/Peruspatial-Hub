# Corrección de seguridad del lector WMS

El portal QGIS bloqueó la versión 1.4.0 original por dos hallazgos de Bandit:
la importación de ElementTree y la llamada a su parser sobre XML remoto.
La validación anterior no incluía ese escáner. Se añadió el escaneo del ZIP
instalable a la integración continua para detectar esta clase de regresión.

## Corrección

Se sustituyó el árbol XML genérico por un lector incremental basado en Expat,
disponible en el Python de QGIS, con estas restricciones explícitas:

- No se descargan DTD externos y no se habilita el análisis de entidades de parámetro.
- Los subconjuntos DTD internos y las declaraciones o referencias a entidades externas
  se rechazan mediante callbacks del propio parser, antes de expandirse.
- Se conserva la compatibilidad con la declaración externa de DTD de WMS 1.1,
  sin resolver su dirección ni cargar su contenido.
- Límites de 25 MiB de entrada, 128 niveles XML, 100.000 elementos,
  20.000 capas y un millón de caracteres por campo.
- Solo se retienen campos del catálogo, no el árbol completo de la respuesta.
- La herramienta de auditoría usa el mismo lector que el panel y el generador.

No se añadieron exclusiones Bandit ni anotaciones para omitir hallazgos.
El plugin no necesita instalar otra biblioteca para esta corrección.

## Comprobaciones

Las 51 pruebas incluyen referencias a archivos y URLs externas, entidades de
parámetro, expansión de entidades, UTF-8/UTF-16/UTF-32, límites de recursos,
XML malformado, namespaces, CDATA y entidades predefinidas permitidas.
Bandit 1.9.4 no encontró hallazgos en los siete archivos Python del plugin.

La prueba con QGIS 3.44.12 real conserva las 27 fuentes configuradas, la carga
de vector REST, MapServer, WMS e ImageServer y los tres renderizados sobre Perú.
El escáner local y estas pruebas no equivalen a una aprobación del portal:
la versión subida debe completar el escaneo automático de QGIS.

## Referencias

- [Referencia oficial de Expat en Python](https://docs.python.org/3/library/pyexpat.html).
- [Reglas XML de Bandit](https://bandit.readthedocs.io/en/latest/blacklists/blacklist_calls.html).
