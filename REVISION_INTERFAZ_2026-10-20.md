# Revisión de PeruSpatial Hub

Fecha: 20 de octubre de 2026. Versión declarada: 1.3.0.

Hay problemas funcionales pendientes, además de oportunidades para organizar mejor la interfaz. Las 12 pruebas existentes pasan, pero no demuestran que las interacciones del panel funcionen correctamente. Esta revisión no modifica el código de la aplicación ni genera un nuevo paquete.

## Errores prioritarios

### 1. La importación de capas sigue bloqueando el hilo de la interfaz

Ubicación: peruspatial_hub_panel.py, métodos add_selected_layer e _instantiate_layer, líneas 1774–1900.

Añadir al mapa llama directamente a _instantiate_layer desde el evento del botón. Esta función consulta metadatos REST y crea proveedores de capas de manera síncrona. Las consultas de metadatos pueden hacer dos intentos de 12 segundos por capa; los proveedores también pueden esperar a la red. Haber movido la exploración de servidores al segundo plano no resuelve esta ruta. QApplication.processEvents entre capas no evita el bloqueo durante cada consulta y permite que otros eventos alteren la selección o el árbol mientras se recorren sus elementos.

Corrección propuesta: capturar primero los datos de las capas seleccionadas, consultar los metadatos mediante tareas y usar una cola controlada para crear y añadir las capas respetando las restricciones de hilos de QGIS. Deshabilitar la acción mientras se importa y permitir cancelar entre elementos.

### 2. El filtro de categorías conserva servidores de otras categorías

Ubicación: peruspatial_hub_panel.py, item_matches_search y filter_tree_item, líneas 1034–1075.

Los hijos de relleno, como Expandir para explorar, no tienen categoría. Se consideran coincidencias y mantienen visible al servidor padre aunque pertenezca a otra categoría. Reproducido ejecutando los métodos reales extraídos del archivo con un árbol simulado: un servidor de Medio Ambiente permaneció visible al seleccionar Geología y Minería.

Corrección propuesta: los elementos de relleno no deben participar en las coincidencias. La categoría debe evaluarse sobre los nodos con datos del catálogo.

### 3. La selección múltiple puede desactivar Añadir al mapa

Ubicación: peruspatial_hub_panel.py, update_buttons_state, líneas 1639–1686.

Con un servidor y dos capas seleccionados, el botón muestra Añadir 2 capas, pero termina deshabilitado si el primer elemento seleccionado es el servidor. La habilitación calculada por cantidad de capas se sobrescribe al evaluar solo ese primer elemento. Reproducido con el método actual.

Corrección propuesta: calcular la acción principal con el conjunto de capas importables seleccionadas, independientemente del elemento usado para mostrar detalles.

### 4. Diferentes capas WMS colisionan en Favoritos

Ubicación: peruspatial_hub_panel.py, _favorite_key, línea 552.

La identidad usa URL y título, pero omite layer_name. El catálogo contiene dos pares reales con esta colisión: Actividad volcánica y Ultimo Sismo. En cada par, los títulos y la URL coinciden, pero los identificadores WMS son diferentes. Guardar una capa impide guardar la otra; quitarla puede eliminar ambas si ya existen en la configuración.

Corrección propuesta: usar tipo, URL e identificador técnico de capa, contemplando los favoritos ya guardados.

### 5. Las acciones del menú contextual pueden operar sobre otra selección

Ubicación: peruspatial_hub_panel.py, show_context_menu, línea 480.

El menú se construye para el elemento bajo el cursor, pero copiar, abrir, registrar y configurar acceso consultan selectedItems por separado. No se garantiza que el elemento bajo el cursor sea el primero seleccionado. El problema también afecta a una selección múltiple: el menú puede describir una capa y operar sobre otro elemento.

Corrección propuesta: conservar la selección múltiple cuando se abre el menú sobre uno de sus elementos; en caso contrario, seleccionar explícitamente el elemento pulsado. Las acciones individuales deben recibir un destino definido.

### 6. Actualizar contenido está disponible para grupos que no pueden recargarse

Ubicación: peruspatial_hub_panel.py, show_context_menu, refresh_node y on_item_expanded.

CONTAINER_TYPES incluye wms_group. Estos grupos se crean con is_loaded=True y reciben la acción Actualizar contenido. Sin embargo, on_item_expanded no carga grupos. Si el grupo estaba cerrado, la recarga borra sus hijos y deja un elemento Recargando sin iniciar una consulta. Si estaba abierto, load_dynamic_node consulta el WMS completo y puede sustituir el subgrupo por todo el catálogo del servidor.

Corrección propuesta: ofrecer recarga únicamente para servidores, carpetas y servicios consultables, o dirigir la recarga del grupo a su servicio de origen.

### 7. La advertencia de datum se pierde al explorar capas de MINCUL

Ubicación: peruspatial_hub_panel.py, load_dynamic_node, líneas 1287–1333.

El servidor raíz conserva crs_warning, pero las carpetas y servicios creados en vivo no heredan ese dato. Sus capas terminan recibiendo False, aunque populate_arcgis_service_layers intente propagar la advertencia. Los resultados del inventario sí pueden conservarla, por lo que una misma fuente presenta avisos distintos según cómo se acceda.

Corrección propuesta: propagar la advertencia a lo largo del árbol y mantenerla como precaución sobre la fuente, sin afirmar un CRS específico que no se haya leído de la capa.

## Organización de la interfaz

La versión actual ya contiene una cabecera compacta, búsqueda en una fila propia, herramientas agrupadas en un menú y estilos que aprovechan la paleta de QGIS. Conviene conservar estas mejoras.

1. Separar Buscar, Explorar y Favoritos en vistas claras. Actualmente el inventario local y el árbol remoto pueden mostrar el mismo contenido con comportamientos diferentes.
2. Mostrar fecha del inventario y cobertura por institución. El archivo incluido fue generado el 16 de agosto de 2026 y registra cero entradas para las dos fuentes de INGEMMET. Esto describe el archivo local, no la disponibilidad actual de sus servidores.
3. Indicar que los resultados están limitados a 200 y permitir cargar más. El contador actual informa el total, pero no permite recorrer los resultados restantes.
4. Mantener un estado visible por servicio: sin consultar, cargando, disponible o error. Añadir Reintentar explícito, porque contraer y expandir resulta poco evidente.
5. Mostrar en detalles institución, tipo de capa, URL completa copiable y CRS cuando se conozca. Los detalles actuales solo muestran el dominio del enlace y no permiten distinguir con facilidad endpoints del mismo servidor.
6. Añadir una acción visible de favoritos para la capa seleccionada; actualmente depende del menú contextual.
7. Restaurar la exploración al reabrir el panel. PeruSpatialHub.run ejecuta collapseAll en cada apertura y anula el estado que el panel acaba de preparar.
8. Reservar el área de progreso para una operación identificable. Verificar servidores y añadir capas comparten la misma barra y pueden sobrescribir su estado mientras se ejecutan simultáneamente.

## Comprobaciones y límites

- Las 12 pruebas existentes aprobaron en una sola ejecución de validación.
- Se reprodujeron el fallo de categorías, el de selección múltiple y las colisiones WMS utilizando métodos del código actual y datos del catálogo incluido.
- La sintaxis del panel se analizó correctamente.
- La disposición gráfica, el escalado y las interacciones nativas de Qt no se probaron visualmente en QGIS. No se encontró un entorno QGIS ejecutable en las ubicaciones consultadas.
- La revisión no consultó los servidores remotos ni considera actuales los errores guardados en el inventario.
- El doble clic requiere una comprobación en QGIS: Qt ya expande y contrae por defecto y el manejador del plugin también cambia ese estado. Referencia: [QTreeView, expandsOnDoubleClick](https://doc.qt.io/qt-6/qtreeview.html#expandsOnDoubleClick-prop).

Orden recomendado: resolver primero la importación bloqueante, el filtro, la selección múltiple y Favoritos; después ajustar menú contextual, recarga de grupos y avisos de datum; finalmente reorganizar navegación y estados.
