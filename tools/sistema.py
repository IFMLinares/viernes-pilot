"""Herramientas del sistema para Viernes (WSL y Linux Nativo)."""
import os
import sys
import shutil
import subprocess
import json
import unicodedata
import re
import difflib

# Mapeo de alias de aplicaciones a nombres de ejecutables para WSL/Windows y Linux Nativo
APP_MAP = {
    "editor": ["code", "code.cmd", "antigravity", "antigravity.exe", "cursor", "cursor.exe"],
    "antigravity": ["antigravity", "antigravity.exe"],
    "opencode": ["opencode", "opencode.exe"],
    "vscode": ["code", "code.cmd"],
    "browser": ["explorer.exe", "xdg-open", "google-chrome", "firefox"],
    "cmd": ["cmd.exe", "bash"],
    "explorer": ["explorer.exe", "xdg-open"]
}


def is_wsl() -> bool:
    """Detecta si el entorno actual es WSL."""
    if sys.platform == "linux":
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    return True
        except FileNotFoundError:
            pass
    return False


def to_windows_path(path: str) -> str:
    """Convierte una ruta de WSL a ruta de Windows si es necesario."""
    if is_wsl() and path:
        try:
            res = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except Exception:
            pass
    return path


def obtener_windows_appdata(roaming: bool = True) -> str:
    """Retorna la ruta de WSL al directorio AppData de Windows (Roaming o Local)."""
    var_name = "$env:APPDATA" if roaming else "$env:LOCALAPPDATA"
    fallback = "Roaming" if roaming else "Local"
    try:
        res = subprocess.run(
            ["powershell.exe", "-Command", f"Write-Output {var_name}"],
            capture_output=True,
            text=True,
            check=True
        )
        win_path = res.stdout.strip()
        if win_path:
            res_wsl = subprocess.run(
                ["wslpath", "-u", win_path],
                capture_output=True,
                text=True,
                check=True
            )
            return res_wsl.stdout.strip()
    except Exception:
        pass
    
    # Buscar dinámicamente en los directorios de usuarios de Windows
    if os.path.exists("/mnt/c/Users"):
        try:
            for item in os.listdir("/mnt/c/Users"):
                # Omitir directorios del sistema de Windows comunes
                if item.lower() in ("default", "public", "all users", "default user"):
                    continue
                p = os.path.join("/mnt/c/Users", item, "AppData", fallback)
                if os.path.isdir(p):
                    return p
        except Exception:
            pass
            
    # Último recurso: usar el usuario de Linux (que a veces coincide con el de Windows)
    try:
        import getpass
        user = getpass.getuser()
        return f"/mnt/c/Users/{user}/AppData/{fallback}"
    except Exception:
        return f"/mnt/c/Users/Default/AppData/{fallback}"


def normalizar_texto(texto: str) -> str:
    """Normaliza el texto quitando acentos, caracteres especiales y convirtiendo a minúsculas."""
    texto_nfkd = unicodedata.normalize('NFKD', texto)
    texto_sin_acentos = "".join([c for c in texto_nfkd if not unicodedata.combining(c)])
    # Reemplazar caracteres no alfanuméricos por espacios
    texto_limpio = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto_sin_acentos).lower()
    # Colapsar espacios múltiples en uno solo
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    return texto_limpio


def obtener_aplicaciones_sistema() -> dict[str, tuple[str, str]]:
    """Obtiene un diccionario de las aplicaciones del sistema.
    Mapea {nombre_normalizado: (nombre_original, app_id_o_desktop_file)}.
    """
    apps = {}
    if is_wsl():
        try:
            result = subprocess.run(
                ["powershell.exe", "-Command", "Get-StartApps | ConvertTo-Json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    data = [data]
                elif not isinstance(data, list):
                    data = []
                
                for item in data:
                    name = item.get("Name")
                    app_id = item.get("AppID")
                    if name and app_id:
                        norm_name = normalizar_texto(name)
                        if norm_name:
                            apps[norm_name] = (name, app_id)
        except Exception:
            pass
    else:
        # Linux Nativo: Parsea directorios de desktop entries
        paths = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
        for path in paths:
            if os.path.exists(path):
                try:
                    for entry in os.listdir(path):
                        if entry.endswith(".desktop"):
                            file_path = os.path.join(path, entry)
                            try:
                                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                                    name = None
                                    name_es = None
                                    in_entry_section = False
                                    for line in f:
                                        line = line.strip()
                                        if line == "[Desktop Entry]":
                                            in_entry_section = True
                                            continue
                                        elif line.startswith("[") and line.endswith("]"):
                                            in_entry_section = False
                                        
                                        if in_entry_section:
                                            if line.startswith("Name[es]=") or line.startswith("Name[es_"):
                                                name_es = line.split("=", 1)[1]
                                            elif line.startswith("Name=") and not name:
                                                name = line.split("=", 1)[1]
                                    
                                    # Indexar con el nombre en español si existe
                                    if name_es:
                                        norm_es = normalizar_texto(name_es)
                                        if norm_es:
                                            apps[norm_es] = (name_es, entry)
                                    if name:
                                        norm_en = normalizar_texto(name)
                                        if norm_en:
                                            apps[norm_en] = (name, entry)
                            except Exception:
                                continue
                except Exception:
                    continue
    return apps


def buscar_coincidencias(query: str, candidatos: dict[str, tuple[str, str]]) -> list[tuple[str, float]]:
    """Busca coincidencias para el query dentro de las claves del diccionario.
    Retorna una lista de tuplas (nombre_normalizado, score) ordenadas por score descendente.
    """
    query_norm = normalizar_texto(query)
    query_words = query_norm.split()
    if not query_words:
        return []
        
    resultados = []
    
    for nom_norm in candidatos.keys():
        nom_words = nom_norm.split()
        
        # 1. Similitud global de toda la cadena
        ratio_global = difflib.SequenceMatcher(None, query_norm, nom_norm).ratio()
        
        # 2. Similitud basada en palabras individuales (maneja palabras en desorden y adiciones)
        word_scores = []
        for qw in query_words:
            best_word_ratio = 0.0
            for nw in nom_words:
                w_ratio = difflib.SequenceMatcher(None, qw, nw).ratio()
                if qw == nw:
                    w_ratio = 1.0
                elif qw in nw or nw in qw:
                    w_ratio = max(w_ratio, 0.85)
                best_word_ratio = max(best_word_ratio, w_ratio)
            word_scores.append(best_word_ratio)
            
        ratio_palabras = sum(word_scores) / len(word_scores) if word_scores else 0.0
        
        # Combinar: 40% global + 60% palabras
        score = (ratio_global * 0.4) + (ratio_palabras * 0.6)
        
        # Boost especial si el query entero es una subcadena exacta
        if query_norm in nom_norm or nom_norm in query_norm:
            score = max(score, 0.8)
            if nom_norm.startswith(query_norm) or query_norm.startswith(nom_norm):
                score = max(score, 0.9)
                
        if score >= 0.55:
            resultados.append((nom_norm, score))
            
    resultados.sort(key=lambda x: x[1], reverse=True)
    return resultados


def abrir_programa(programa: str, ruta: str = None) -> str:
    """Abre un programa en el sistema resolviéndolo dinámicamente o por alias, opcionalmente abriendo una ruta."""
    prog_lower = programa.lower().strip()
    ruta_abs = os.path.abspath(os.path.expanduser(ruta)) if ruta else None
    
    # 1. Determinar candidatos según el mapeo de alias
    if prog_lower in APP_MAP:
        candidates = APP_MAP[prog_lower]
        if is_wsl() or sys.platform == "win32":
            expanded = []
            for c in candidates:
                expanded.append(c)
                if not c.lower().endswith((".exe", ".cmd", ".bat", ".lnk")):
                    expanded.extend([f"{c}.exe", f"{c}.cmd", f"{c}.bat"])
            candidates = expanded
        
        # Buscar si el candidato existe en el PATH
        resolved_candidate = None
        for candidate in candidates:
            path_check = shutil.which(candidate)
            if path_check:
                resolved_candidate = candidate
                break
                
        if resolved_candidate:
            try:
                cmd = [resolved_candidate]
                if ruta_abs:
                    cmd.append(to_windows_path(ruta_abs))
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                info_ruta = f" apuntando a '{ruta_abs}'" if ruta_abs else ""
                return f"Lanzando el programa alias '{programa}' ('{resolved_candidate}'){info_ruta} en segundo plano con éxito."
            except Exception as e:
                return f"Error al intentar ejecutar el alias '{resolved_candidate}': {e}"

    # 2. Verificar si es un ejecutable directo en el PATH
    path_check = shutil.which(programa)
    if path_check:
        try:
            cmd = [path_check]
            if ruta_abs:
                cmd.append(to_windows_path(ruta_abs))
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            info_ruta = f" apuntando a '{ruta_abs}'" if ruta_abs else ""
            return f"Lanzando el ejecutable directo '{programa}'{info_ruta} en segundo plano con éxito."
        except Exception as e:
            return f"Error al intentar ejecutar el ejecutable '{programa}': {e}"

    # 3. Resolución dinámica mediante el menú de aplicaciones del sistema (Fuzzy Matching)
    apps = obtener_aplicaciones_sistema()
    if not apps:
        return f"No se pudo encontrar '{programa}' en el PATH y no se pudieron cargar las aplicaciones del sistema."

    coincidencias = buscar_coincidencias(programa, apps)
    
    if not coincidencias:
        return f"No se encontró ninguna aplicación en el sistema que coincida con '{programa}'."

    # Lógica de decisión según scores
    best_norm, best_score = coincidencias[0]
    best_orig, best_ref = apps[best_norm]

    # Caso 1: Coincidencia de alta confianza (score >= 0.8) o solo hay una opción
    if best_score >= 0.8 or len(coincidencias) == 1:
        # Lanzar la aplicación
        try:
            if is_wsl():
                # En WSL lanzamos UWP o Win32 por AppID usando explorer.exe shell:AppsFolder\<AppID>
                cmd = ["explorer.exe", f"shell:AppsFolder\\{best_ref}"]
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            else:
                # En Linux nativo lanzamos usando gtk-launch con el archivo desktop
                cmd = ["gtk-launch", best_ref]
                if ruta_abs:
                    cmd.append(ruta_abs)
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            info_ruta = f" apuntando a '{ruta_abs}'" if (ruta_abs and not is_wsl()) else ""
            return f"Lanzando '{best_orig}'{info_ruta} en segundo plano con éxito."
        except Exception as e:
            return f"Error al lanzar '{best_orig}': {e}"

    # Caso 2: Coincidencia ambigua o de confianza media
    candidatos_validos = []
    for name_norm, score in coincidencias:
        if score >= 0.55:
            orig_name, _ = apps[name_norm]
            if orig_name not in candidatos_validos:
                candidatos_validos.append(orig_name)
    
    if len(candidatos_validos) > 1:
        lista_opciones = ", ".join([f"'{c}'" for c in candidatos_validos[:3]])
        return (
            f"AMBIGUO: Encontré múltiples coincidencias posibles para '{programa}': {lista_opciones}. "
            f"Por favor, preguntale al usuario cuál de ellas prefiere abrir."
        )

    return (
        f"AMBIGUO: ¿Quisiste decir '{best_orig}'? "
        f"Confirmá con el usuario antes de abrir esta aplicación."
    )


def abrir_terminal(carpeta: str, comando: str = None) -> str:
    """Abre una nueva pestaña o ventana de terminal en el directorio especificado, ejecutando opcionalmente un comando."""
    carpeta_abs = os.path.abspath(os.path.expanduser(carpeta))
    if not os.path.exists(carpeta_abs):
        return f"Error: La ruta '{carpeta_abs}' no existe en el sistema."

    folder_name = os.path.basename(carpeta_abs) or "run"
    folder_name_clean = re.sub(r'[^a-zA-Z0-9_]', '_', folder_name)

    if is_wsl():
        # 1. Resolver rutas de Windows
        win_carpeta = to_windows_path(carpeta_abs)
        roaming = obtener_windows_appdata(roaming=True)
        local = obtener_windows_appdata(roaming=False)
        
        # Warp Configurations directory on Windows
        warp_configs_dir = os.path.join(roaming, "warp", "Warp", "data", "tab_configs")
        
        if os.path.exists(warp_configs_dir):
            # Usar Warp Terminal
            if comando:
                # Escribir un archivo TOML de Tab Config para Warp
                config_filename = f"viernes_{folder_name_clean}.toml"
                config_path = os.path.join(warp_configs_dir, config_filename)
                
                # Escapar rutas y comandos para TOML
                dir_val = win_carpeta.replace("\\", "\\\\").replace('"', '\\"')
                cmd_val = comando.replace("\\", "\\\\").replace('"', '\\"')
                
                toml_content = f"""# Configuración autogenerada por Viernes
name = "viernes_{folder_name_clean}"

[[panes]]
id = "main"
type = "terminal"
directory = "{dir_val}"
commands = ["{cmd_val}"]
"""
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(toml_content)
                    
                    # Ejecutar vía protocolo URI de Warp en Windows
                    subprocess.Popen(
                        ["powershell.exe", "-Command", f"Start-Process 'warp://tab_config/viernes_{folder_name_clean}'"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return f"Nueva pestaña de Warp abierta ejecutando '{comando}' en '{carpeta_abs}' (vía Tab Config)."
                except Exception as e:
                    return f"Error al generar Tab Config de Warp: {e}. Reintentando con fallback..."
            else:
                # Lanzar pestaña interactiva simple en Warp
                try:
                    subprocess.Popen(
                        ["powershell.exe", "-Command", f"Start-Process 'warp://action/new_tab?path={win_carpeta}'"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return f"Nueva pestaña de Warp abierta parada en '{carpeta_abs}'."
                except Exception as e:
                    return f"Error al lanzar pestaña en Warp: {e}. Reintentando con fallback..."

        # 2. Fallback a Windows Terminal (wt.exe)
        wt_path = os.path.join(local, "Microsoft", "WindowsApps", "wt.exe")
        distro = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
        
        if os.path.exists(wt_path):
            try:
                if comando:
                    args = [
                        wt_path, "-d", win_carpeta, "wsl.exe", "-d", distro,
                        "-e", "bash", "-c", f"cd {carpeta_abs} && {comando}; exec bash"
                    ]
                else:
                    args = [wt_path, "-d", win_carpeta, "wsl.exe", "-d", distro]
                
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return f"Nueva pestaña de Windows Terminal abierta en '{carpeta_abs}'."
            except Exception:
                pass

        # 3. Fallback a Conhost (consola clásica de Windows)
        try:
            if comando:
                args = [
                    "conhost.exe", "wsl.exe", "-d", distro,
                    "-e", "bash", "-c", f"cd {carpeta_abs} && {comando}; exec bash"
                ]
            else:
                args = ["conhost.exe", "wsl.exe", "-d", distro]
            
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return f"Nueva ventana de consola abierta en '{carpeta_abs}' (usando conhost.exe)."
        except Exception as e:
            return f"Error al intentar abrir la consola clásica de Windows: {e}"

    else:
        # Linux Nativo: Soporte para Warp y otros emuladores de terminal
        warp_configs_dir = os.path.expanduser("~/.local/share/warp-terminal/tab_configs")
        warp_in_path = shutil.which("warp-terminal")
        
        if warp_in_path or os.path.exists(warp_configs_dir):
            os.makedirs(warp_configs_dir, exist_ok=True)
            
            if comando:
                config_filename = f"viernes_{folder_name_clean}.toml"
                config_path = os.path.join(warp_configs_dir, config_filename)
                
                dir_val = carpeta_abs.replace("\\", "\\\\").replace('"', '\\"')
                cmd_val = comando.replace("\\", "\\\\").replace('"', '\\"')
                
                toml_content = f"""# Configuración autogenerada por Viernes
name = "viernes_{folder_name_clean}"

[[panes]]
id = "main"
type = "terminal"
directory = "{dir_val}"
commands = ["{cmd_val}"]
"""
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(toml_content)
                    
                    subprocess.Popen(
                        ["xdg-open", f"warp://tab_config/viernes_{folder_name_clean}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return f"Nueva pestaña de Warp abierta ejecutando '{comando}' en '{carpeta_abs}' (vía Tab Config)."
                except Exception:
                    pass
            else:
                try:
                    subprocess.Popen(
                        ["xdg-open", f"warp://action/new_tab?path={carpeta_abs}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return f"Nueva pestaña de Warp abierta parada en '{carpeta_abs}'."
                except Exception:
                    pass

        # 2. Fallbacks de Linux
        terminals = ["gnome-terminal", "konsole", "alacritty", "kitty", "xfce4-terminal", "xterm"]
        for term in terminals:
            path_check = shutil.which(term)
            if path_check:
                try:
                    if term == "gnome-terminal":
                        if comando:
                            cmd = ["gnome-terminal", "--working-directory", carpeta_abs, "--", "bash", "-c", f"{comando}; exec bash"]
                        else:
                            cmd = ["gnome-terminal", "--working-directory", carpeta_abs]
                    elif term == "konsole":
                        if comando:
                            cmd = ["konsole", "--workdir", carpeta_abs, "-e", "bash", "-c", f"{comando}; exec bash"]
                        else:
                            cmd = ["konsole", "--workdir", carpeta_abs]
                    elif term == "alacritty":
                        if comando:
                            cmd = ["alacritty", "--working-directory", carpeta_abs, "-e", "bash", "-c", f"{comando}; exec bash"]
                        else:
                            cmd = ["alacritty", "--working-directory", carpeta_abs]
                    elif term == "kitty":
                        if comando:
                            cmd = ["kitty", "--directory", carpeta_abs, "bash", "-c", f"{comando}; exec bash"]
                        else:
                            cmd = ["kitty", "--directory", carpeta_abs]
                    elif term == "xfce4-terminal":
                        if comando:
                            cmd = ["xfce4-terminal", "--working-directory", carpeta_abs, "-e", f"bash -c '{comando}; exec bash'"]
                        else:
                            cmd = ["xfce4-terminal", "--working-directory", carpeta_abs]
                    else: # xterm
                        if comando:
                            cmd = ["xterm", "-hold", "-e", f"cd '{carpeta_abs}' && {comando}"]
                        else:
                            cmd = ["xterm", "-hold", "-e", f"cd '{carpeta_abs}' && exec bash"]
                            
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    return f"Nueva pestaña de '{term}' abierta en '{carpeta_abs}'."
                except Exception:
                    continue

        return f"No se pudo encontrar un emulador de terminal compatible en tu sistema Linux."


def mostrar_notificacion(titulo: str, mensaje: str) -> str:
    """Muestra una notificación nativa en el escritorio (WSL o Linux Nativo)."""
    # Escapar comillas simples para los comandos de script
    titulo_esc = titulo.replace("'", "''")
    mensaje_esc = mensaje.replace("'", "''")

    if is_wsl():
        # Notificación nativa de Windows vía PowerShell ejecutada desde WSL
        ps_script = (
            f"[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms'); "
            f"$notification = New-Object System.Windows.Forms.NotifyIcon; "
            f"$notification.Icon = [System.Drawing.SystemIcons]::Information; "
            f"$notification.BalloonTipTitle = '{titulo_esc}'; "
            f"$notification.BalloonTipText = '{mensaje_esc}'; "
            f"$notification.Visible = $True; "
            f"$notification.ShowBalloonTip(5000)"
        )
        try:
            subprocess.Popen(
                ["powershell.exe", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return "Notificación de Windows enviada con éxito desde WSL."
        except Exception as e:
            return f"Error al enviar notificación de Windows desde WSL: {e}"
    else:
        # Notificación nativa de Linux (CachyOS / GNOME / KDE)
        if shutil.which("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", titulo, mensaje],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return "Notificación enviada con éxito mediante notify-send."
            except Exception as e:
                return f"Error al lanzar notify-send: {e}"
        else:
            return "No se pudo enviar la notificación (notify-send no está instalado en este sistema Linux)."
