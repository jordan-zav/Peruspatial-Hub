# Inventario local

`catalog.json` es un archivo generado que permite buscar servicios y capas sin consultar los geoportales mientras el usuario escribe.

Para actualizarlo desde una estación de mantenimiento con acceso a internet:

```bash
python scripts/build_catalog.py
python -m pytest
```

El generador conserva el estado de cada fuente. Un estado `partial` indica que una rama no respondió, exigió autenticación o presentó un problema TLS; nunca se desactiva la validación de certificados para completar el inventario.

No edite `catalog.json` manualmente.
