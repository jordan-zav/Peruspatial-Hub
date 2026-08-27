# Changelog

## 1.3.0 - 2026-08-26

- Las consultas de catálogos remotos y la verificación masiva se ejecutan en segundo plano para evitar bloqueos de QGIS.
- Corregida la recarga de servidores cuando el nodo ya estaba expandido.
- Corregida la copia de URL al portapapeles.

## 1.2.0 - 2026-08-18

- Menú contextual (clic derecho) con opciones específicas para servidores, carpetas, capas y autenticación.
- Nueva sección fija de **Favoritos** persistente en la configuración de QGIS.
- Carga de capas por lotes mediante multi-selección (`Ctrl+Clic` / `Shift+Clic`).
- Recarga dinámica de servidores y subcarpetas en vivo sin reiniciar QGIS.
- Verificador masivo de salud y conectividad de todos los servidores oficiales del catálogo.
- Barra de progreso visual integrada para feedback de tareas en segundo plano.
- Asistente interactivo de empaquetado y validación de estándares QGIS (`crear_release.bat`).
- User-Agent dinámico sincronizado con la versión de `metadata.txt`.

## 1.1.2 - 2026-08-16

- Sustituye la exploración remota automática por búsqueda sobre un inventario local.
- Evita solicitudes bloqueantes mientras se escribe en el buscador.
- Incluye más de 8,000 servicios y capas REST/WMS inventariados.
- Limita la representación a 200 resultados y aplica un debounce de 180 ms.

## 1.1.1 - 2026-07-17

- Catálogo ampliado de servicios públicos peruanos.
- Exploración y carga de directorios ArcGIS REST y servicios WMS.
- Accesos NDVI y mejoras del empaquetado.

## 1.0.2

- Integración del directorio ArcGIS REST del IGP.

## 1.0.0

- Primera versión estable bajo GPLv3.
