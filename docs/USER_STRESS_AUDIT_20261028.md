# Pruebas de uso y estrés de la interfaz

Fecha: 28 de octubre de 2026. QGIS 3.44.12, Qt 5.15, Windows.

Se probaron recorridos de usuario con widgets Qt, tareas QGIS y el gestor real
de plugins. Los retrasos y errores de los casos de estrés usan respuestas
controladas locales. Las comprobaciones con servicios públicos se ejecutaron
aparte, con cargas y renderizados representativos.

## Fallos encontrados y corregidos

La primera ejecución de diez recorridos nuevos terminó con siete aprobados y
tres fallos reproducibles:

| Acción del usuario | Fallo observado | Corrección |
| --- | --- | --- |
| Cerrar y reabrir el panel | Se reconstruían los resultados y se perdían las carpetas abiertas y la selección | Una búsqueda sin cambios conserva su árbol. El controlador deja de cerrar todas las ramas al mostrar el panel |
| Seleccionar la misma capa en resultados y favoritos y pulsar Añadir | Se añadía dos veces el mismo dataset | La carga y su contador usan la identidad del recurso para eliminar duplicados de la misma selección |
| Seleccionar una capa y pulsar Enter | No se añadía al proyecto | La activación nativa de Qt atiende tanto el teclado como el doble clic, con una sola carga por activación |

La deduplicación opera dentro de una selección. Una nueva petición del usuario
puede volver a añadir el dataset al proyecto. Los favoritos WMS con títulos
iguales y distintos nombres de capa continúan siendo recursos diferentes.

## Campaña final

Se ejecutaron los 39 casos de interfaz anteriores y doce recorridos de estrés:
51 casos aprobados. Una segunda secuencia repitió los doce recorridos con otro
orden y el doble de iteraciones; todos aprobaron. Semillas 20261028 y 8731,
con ocho y dieciséis iteraciones respectivamente.

Los siguientes totales suman ambas secuencias:

| Recorrido | Volumen comprobado |
| --- | --- |
| Cambios rápidos de búsqueda y categoría | 600 ciclos, sin peticiones de red involuntarias |
| Abrir y cerrar carpetas y grupos | 360 ciclos sobre seis grupos y 48 capas; cada carga inicial hizo dos consultas de metadatos |
| Respuestas simultáneas de servicios | 192 respuestas asociadas al padre correcto, en orden de llegada variable |
| Cambiar de búsqueda con una respuesta pendiente | 24 sustituciones sin sobrescribir los resultados nuevos |
| Cerrar y reabrir el panel | 24 ciclos conservando selección y ramas |
| Tiempo de espera y reintento | 24 ciclos de fallo y recuperación |
| Cambiar tamaño, desacoplar y volver a acoplar | 48 ciclos conservando selección, columnas y controles |
| Reconstruir, quitar y volver a añadir favoritos | 24 ciclos con 24 recursos de títulos repetidos |
| Añadir lotes mientras cambia la búsqueda | 192 datasets seleccionados: 163 cargas correctas y 29 fallos simulados, agrupados por lote |
| Descargar el plugin durante tareas pendientes | Dos descargas con ocho tareas de servicio pendientes cada una |
| Selección duplicada y activación por teclado | Una carga por recurso seleccionado y una por activación |

Los escenarios verifican también iconos, columnas Tipo de dato/Fuente,
selección tras desplazarse, límites de resultados, categorías, ausencia de
excepciones en señales Qt y descarte de respuestas que ya no corresponden
a la pantalla actual.

## QGIS de escritorio y proveedores

El ZIP se instaló en un perfil de prueba mediante el gestor real de QGIS.
Pasaron las diez comprobaciones de escritorio, incluidas doce recargas del
plugin manteniendo las capas del proyecto. Cerrar y reabrir el panel conservó
una carpeta abierta y la capa seleccionada. El proceso terminó con código 0.

Se comprobaron seis proveedores remotos y cinco renderizados: vector y mapa
de MIDAGRI, WMS de SENAMHI, ImageServer ASTER de INGEMMET y el mapa geológico
100K tanto completo como por subcapa en modo ráster. Las cargas y los
renderizados terminaron sin errores. Ruff, 113 pruebas Python y Bandit sobre
el paquete distribuido aprobaron; Bandit no encontró incidencias.

## Repetición

Con el Python de QGIS:

~~~text
python scripts/qgis_ui_checks.py --stress --stress-seed 20261028 --stress-iterations 8 --output RUTA_DE_SALIDA
python scripts/qgis_ui_checks.py --stress --stress-seed 8731 --stress-iterations 16 --output OTRA_RUTA_DE_SALIDA
python scripts/qgis_desktop_checks.py --qgis-bin RUTA_DEL_EJECUTABLE_QGIS --install --reload-cycles 12 --output RUTA_DE_ESCRITORIO
~~~

La segunda orden repite también los casos de interfaz anteriores. En la
campaña registrada se seleccionaron solo los doce casos de estrés para esa
segunda semilla mediante opciones --case.

Cada ejecución guarda ui-results.json y capturas por caso. El escritorio
produce desktop-results.json y process-result.json; los proveedores guardan
qgis-smoke.json e imágenes renderizadas. Los perfiles y datos de prueba quedan
fuera del repositorio y de la configuración habitual del usuario.

La integración continua ejecuta estos recorridos de estrés con ocho
iteraciones y ocho recargas de escritorio sobre el ZIP instalable.
