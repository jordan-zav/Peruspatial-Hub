# Inventario local

catalog.json es un archivo generado que permite buscar servicios y capas sin consultar los geoportales mientras el usuario escribe.

Para actualizarlo desde una estación de mantenimiento con acceso a internet:

~~~text
python scripts/build_catalog.py
python -m pytest
~~~

El generador conserva el estado y la fecha de revisión de cada fuente. Un estado partial indica que alguna rama no respondió, exigió autenticación o presentó un problema de red o TLS. Nunca se desactiva la validación de certificados para completar el inventario.

Si una revisión falla, las entradas anteriores de esa fuente se conservan con stale y last_verified_at. El panel las identifica como sin verificar. Una revisión completa sí puede retirar entradas que ya no se publican. Se preservan los parámetros de proveedor de servicios WMS y se deduplican los endpoints repetidos.

La opción --source permite actualizar una institución o URL concreta. La opción --previous permite conservar un catálogo de referencia al escribir en otra ruta mediante --output. El archivo final se sustituye de forma atómica, tras construir el documento completo. Cada fuente mantiene su propia fecha aunque la actualización sea selectiva.

No edite catalog.json manualmente. Consulte docs/AUDIT_20261028.md para conocer el alcance y los límites de la auditoría.
