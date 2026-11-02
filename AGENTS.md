# Instrucciones del proyecto

Estas reglas complementan las instrucciones existentes de las carpetas superiores.

- No uses backticks ni caracteres de acento sueltos en reportes Word o Markdown.
- Usa D:\DevResources como raíz de recursos, cachés y temporales de desarrollo. Reutiliza los SDK y dependencias existentes.
- Conserva el código fuente y las copias temporales de código en E:, conforme a las instrucciones de la carpeta superior.
- Guarda las cachés compartibles en D:\DevResources\Shared y separa los temporales de herramientas por proyecto y ejecución en D:\DevResources\Sessions.
- Configura TEMP y TMP únicamente para cada sesión.
- Usa los lanzadores y bloqueos existentes: máximo dos compilaciones pesadas simultáneas y exclusión entre tareas que escriban el mismo workspace. No cierres otros programas.
- No dupliques recursos en C: ni otros discos. Conserva código, datos, autenticación y enlaces de compatibilidad.
- Limpia únicamente archivos regenerables e inactivos después de verificar sus referencias. No toques DriveFS.
- Conserva estas instrucciones al añadir otras nuevas.

## Instrucciones locales conservadas

Antes de cambiar recursos comprueba unidades, instrucciones, remotos, ramas y cambios locales. Actualiza mediante pull con avance rapido y conserva cambios; informa divergencias sin reset ni cambio de rama.
Usa la raiz local D:\DevResources cuando sea valida; si no lo es, solicita elegir otra raiz. Reutiliza SDK y caches compatibles en Shared, separa estado mutable por proyecto y usa Sessions unicas por ejecucion.
Usa DEVRESOURCES_RUN.cmd para comandos de desarrollo; las configuraciones .devresources son locales y no deben subirse. TEMP y TMP se cambian solo para la sesion y sus hijos. Coordina bloqueos por workspace y maximo dos compilaciones pesadas.
No detengas procesos ajenos. No modifiques DriveFS, datos ni sincronizacion de Google Drive. Conserva codigo, datos, autenticacion, claves y enlaces de compatibilidad.
Comprueba rutas y lanzadores antes de consolidar. Antes de cualquier eliminacion presenta candidatos y espera autorizacion expresa; verifica referencias, copias, destinos fisicos e inactividad. No ejecutes limpiezas automaticas durante esta auditoria.
No afirmes compilaciones que no ejecutaste. Los informes Markdown y Word no deben contener backticks.

## Rutas según el equipo

Las referencias a E: corresponden a la laptop. En esta PC, el código y los scripts auxiliares permanecen en O:\0. Projects; se reutilizan los clones existentes. D:\DevResources se reserva para recursos, cachés, temporales de herramientas e informes. Verifica la raíz real antes de operar y conserva todas las instrucciones anteriores.
