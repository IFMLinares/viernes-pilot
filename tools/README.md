# Tools Module

[English](#) | [Español](README.es.md)

The `tools` module provides system-level integration scripts. It enables Viernes to open desktop applications, translate file paths between WSL and Windows, send desktop alerts, and orchestrate terminals.

## File Breakdown

### sistema.py

This file contains the core OS-level execution utilities.

- **abrir_programa(programa, ruta)**:
  - Resolves friendly names (e.g., "calculadora", "spotify") to executable files or App IDs.
  - On WSL, it fetches host programs by calling PowerShell's `Get-StartApps`.
  - On native Linux, it queries system applications via desktop entry files (`.desktop`).
  - Text normalization is applied to strip accents, lowercase strings, and remove special characters.
  - A hybrid matching algorithm uses substring checks and `difflib.SequenceMatcher` to rate compatibility and select the best candidate.
  - Supports an optional `ruta` parameter to open the chosen application (e.g. an IDE) directly inside a specific folder.

- **abrir_terminal(carpeta, comando)**:
  - Configures and opens a terminal workspace.
  - Supports triggering advanced layout configuration schemas (if supported on the host system) or falling back to standard terminal emulators.
  - The fallback mechanism supports launching Windows Terminal (`wt.exe`), Windows Console Host (`conhost.exe`), or standard Linux terminal clients (`gnome-terminal`, `konsole`, `kitty`, `alacritty`), starting an interactive shell session in the target directory and executing the specified command.

- **to_windows_path(path)**:
  - Uses `wslpath -w` to safely translate WSL Unix-style paths into Windows-compatible UNC paths (`\\wsl.localhost\Ubuntu\...`).

- **obtener_windows_appdata(roaming)**:
  - Dynamically retrieves the WSL mount path for the active Windows user's AppData directory (Roaming or Local). It first queries PowerShell; if that fails, it scans `/mnt/c/Users/` for a valid directory structure, ensuring no hardcoded user directories exist in the code.

- **mostrar_notificacion(titulo, mensaje)**:
  - Triggers native desktop notification banners. Uses PowerShell commands on Windows/WSL and `notify-send` on native Linux environments.
