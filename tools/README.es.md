# Módulo de Herramientas

[Español](#) | [English](README.md)

El módulo `tools` proporciona los scripts de integración a nivel del sistema operativo. Permite a Viernes abrir aplicaciones de escritorio, traducir rutas de archivos entre WSL y Windows, enviar alertas al escritorio y orquestar terminales.

## Desglose de Archivos

### sistema.py

Este archivo contiene las utilidades de ejecución a nivel de sistema operativo.

- **abrir_programa(programa, ruta)**:
  - Resuelve nombres amigables (ej: "calculadora", "spotify") a ejecutables reales o App IDs del sistema.
  - En WSL, recupera las aplicaciones del anfitrión llamando a `Get-StartApps` a través de PowerShell.
  - En Linux nativo, consulta las aplicaciones del sistema mediante los archivos de entrada de escritorio (`.desktop`).
  - Aplica normalización de texto para eliminar acentos, convertir a minúsculas y omitir caracteres especiales.
  - Un algoritmo de coincidencia híbrido utiliza búsquedas por subcadena y `difflib.SequenceMatcher` para calcular el porcentaje de similitud y elegir la mejor coincidencia.
  - Admite un parámetro opcional `ruta` para abrir la aplicación elegida (ej. un IDE) apuntando a una carpeta específica.

- **abrir_terminal(carpeta, comando)**:
  - Configura y abre un espacio de trabajo en la terminal.
  - Permite disparar esquemas avanzados de configuración de pestañas (si el sistema operativo anfitrión cuenta con soporte) o delegar en emuladores de terminal estándares.
  - El mecanismo de respaldo permite lanzar de manera interactiva Windows Terminal (`wt.exe`), Windows Console Host (`conhost.exe`) o clientes de terminal estándar de Linux (`gnome-terminal`, `konsole`, `kitty`, `alacritty`), iniciando el shell en la carpeta especificada y ejecutando el comando indicado.

- **to_windows_path(path)**:
  - Utiliza la herramienta `wslpath -w` para traducir de forma segura rutas Unix de WSL a rutas UNC compatibles con Windows (`\\wsl.localhost\Ubuntu\...`).

- **obtener_windows_appdata(roaming)**:
  - Obtiene dinámicamente la ruta en WSL al directorio AppData de Windows (Roaming o Local). Intenta realizar la consulta mediante PowerShell; si esto falla, escanea `/mnt/c/Users/` buscando estructuras válidas, garantizando la portabilidad del código al no depender de nombres de usuario fijos.

- **mostrar_notificacion(titulo, mensaje)**:
  - Lanza notificaciones nativas en el escritorio. Utiliza PowerShell en Windows/WSL y `notify-send` en entornos Linux nativos.
