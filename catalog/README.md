# Inventario local

catalog.json es un archivo generado que permite buscar servicios y capas sin consultar los geoportales mientras el usuario escribe.

Para actualizarlo desde una estación de mantenimiento con acceso a internet:

~~~text
python scripts/build_catalog.py
python -m pytest
~~~

El generador conserva el estado y la fecha de revisión de cada fuente. Un estado partial indica que alguna rama no respondió, exigió autenticación o presentó un problema de red o TLS. Nunca se desactiva la validación de certificados para completar el inventario.

Si una revisión falla, las entradas anteriores de esa fuente se conservan con stale y last_verified_at. El panel las identifica como sin verificar. Una revisión completa sí puede retirar entradas que ya no se publican. Se preservan los parámetros de proveedor de servicios WMS y se deduplican los endpoints repetidos.

La cobertura se registra también por servicio. Si un servicio responde con un inventario válido, se actualizan sus subcapas aunque otra carpeta de la misma fuente falle. Así no se mantienen como capas los IDs que ahora son grupos. Las entradas de servicios inaccesibles se conservan sin atribuirles una nueva fecha de verificación. Durante una actualización parcial, que un servicio falte en el directorio público no basta para eliminarlo: podría estar protegido.

Las entradas pueden incluir tipo de dato, geometría, número de campos, capacidades, extensión, referencia espacial y ruta completa de grupos. metadata_level distingue una simple enumeración del directorio de los metadatos de servicio o capa. Las tablas sin geometría no heredan el CRS espacial del servicio. Las advertencias de campos duplicados describen el esquema publicado por la institución; no se renombra ni se inventa un campo para ocultar el problema.

La auditoría profunda conserva una instantánea de respuestas y exporta los metadatos de capas y esquemas de campos:

~~~text
python scripts/audit_inventory.py --output RUTA_DE_AUDITORIA
python scripts/audit_inventory.py --output RUTA_DE_AUDITORIA --offline
~~~

La segunda orden analiza las respuestas ya guardadas y mantiene su fecha original; no acredita una comprobación de red nueva. Para comparar con una copia anterior concreta se puede añadir --catalog RUTA_DEL_CATALOGO_ANTERIOR. La comprobación de CRS con el Python de QGIS está en scripts/qgis_inventory_checks.py.

La opción --source permite actualizar una institución o URL concreta. La opción --previous permite conservar un catálogo de referencia al escribir en otra ruta mediante --output. El archivo final se sustituye de forma atómica, tras construir el documento completo. Cada fuente mantiene su propia fecha aunque la actualización sea selectiva.

No edite catalog.json manualmente. Consulte docs/AUDIT_20261028.md para conocer el alcance y los límites de la auditoría.
