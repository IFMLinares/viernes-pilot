"""English/Spanish terminal presentation; never translates stored records."""
import os
import re
from datetime import date

MESSAGES = {
    "welcome": ("Viernes — general questions and commitments; /help for commands; /confirm applies a proposal.",
                "Viernes — preguntas generales y compromisos; /help muestra comandos; /confirm aplica una propuesta."),
    "prompt": ("you: ", "tú: "),
    "goodbye": ("Goodbye. Unconfirmed proposals were not saved.", "Hasta luego. Las propuestas sin confirmar no se guardaron."),
    "cancelled": ("Cancelled. No changes saved.", "Cancelado. No se guardaron cambios."),
    "no_proposal": ("No proposal to confirm.", "No hay una propuesta para confirmar."),
    "saved": ("Saved", "Guardado"),
    "pending": ("A proposal is pending. Use /confirm or /cancel before a new request.",
                "Hay una propuesta pendiente. Usa /confirm o /cancel antes de otra solicitud."),
    "offline": ("Ollama unavailable. Use /new, /list, /edit or /done; /help shows syntax.",
                "Ollama no está disponible. Usa /new, /list, /edit o /done; /help muestra la sintaxis."),
    "limit": ("Clarification limit reached. Please restate the full request.",
              "Se alcanzó el límite de aclaraciones. Vuelve a escribir la solicitud completa."),
    "proposal": ("Proposal · Not saved yet", "Propuesta · Todavía no guardada"),
    "confirm": ("/confirm to save · /cancel to discard", "/confirm para guardar · /cancel para descartar"),
    "create": ("Create", "Crear"), "edit": ("Edit", "Editar"), "complete": ("Complete", "Completar"),
    "area": ("Area", "Área"), "project": ("Project", "Proyecto"), "due": ("Deadline", "Fecha límite"),
    "status": ("Status", "Estado"), "university": ("University", "Universidad"),
    "work": ("Work", "Trabajo"), "personal": ("Personal", "Personal"),
    "pending_status": ("Pending", "Pendiente"), "completed": ("Completed", "Completado"),
    "no_date": ("No deadline", "Sin fecha límite"), "empty": ("No commitments found.", "No hay compromisos."),
    "error": ("Could not process the request. Check the input; use /help or /cancel.",
              "No se pudo procesar la solicitud. Revisa los datos; usa /help o /cancel."),
    "network_error": ("Could not reach Ollama. Offline commands are still available.",
                      "No se pudo contactar a Ollama. Los comandos sin IA siguen disponibles."),
    "storage_error": ("Could not access commitment storage. Check the path and permissions.",
                      "No se pudo acceder a los compromisos. Revisa la ruta y los permisos."),
    "autostart_error": ("VIERNES_OLLAMA_AUTOSTART must be true or false.",
                        "VIERNES_OLLAMA_AUTOSTART debe ser true o false."),
    "timeout_error": ("VIERNES_OLLAMA_STARTUP_TIMEOUT must be numeric.",
                      "VIERNES_OLLAMA_STARTUP_TIMEOUT debe ser un número."),
    "all_areas": ("All areas", "Todas las áreas"),
    "history": ("Full history", "Historial completo"),
    "recent": ("Recent and upcoming", "Recientes y próximos"),
    "overdue": ("Older overdue pending", "Vencidos anteriores pendientes"),
    "undated": ("Pending without a deadline", "Pendientes sin fecha"),
    "empty_scope": ("No commitments in the queried scope.", "No hay compromisos en el alcance consultado."),
    "clarify_area": ("Which area: university, work or personal?", "¿De qué área: universidad, trabajo o personal?"),
    "clarify_date": ("What is the complete date or date range, including the year?",
                     "¿Cuál es la fecha o el período completo, incluido el año?"),
    "clarify_id": ("Which commitment ID? Use /list to find it.", "¿Cuál es el ID del compromiso? Usa /list para consultarlo."),
    "clarify_scope": ("Use the usual period, a date range, or explicitly request full history?",
                      "¿Quieres el período habitual, un rango de fechas o consultar explícitamente todo el historial?"),
    "clarify_request": ("Would you like to create, list, edit or complete a commitment?",
                        "¿Quieres registrar, consultar, editar o completar un compromiso?"),
    "general_reply": ("AI reply · General information (no commitment lookup)",
                      "Respuesta de IA · Información general (sin consultar tus compromisos)"),
}


def text(key, language):
    return MESSAGES[key][language == "es"]


def initial_language():
    locale = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "en")
    return "es" if locale.lower().startswith("es") else "en"


def input_language(value, previous):
    """Conservative fallback for offline/failed requests; model metadata handles normal input."""
    words = set(re.findall(r"[^\W\d_]+", value.lower()))
    spanish = words & set((
        "tengo entregar tarea tareas parcial pendientes necesito quiero mañana ayer sí "
        "español noviembre mostrar mis guardar cancelar el la los las que de para una"
    ).split())
    english = words & set((
        "have need want submit assignment assignments exam pending tomorrow yesterday "
        "yes english november show save cancel the my please with for this an to"
    ).split())
    if len(spanish) == len(english):
        return previous
    return "es" if len(spanish) > len(english) else "en"


def help_text(language):
    if language == "en":
        intro = "Commands (also available offline):"
        descriptions = ["Show pending and completed commitments.", "Propose changed fields; null removes a date.",
                        "Propose completion.", "Apply exactly the displayed proposal.",
                        "Discard proposal and clarification context.", "Show commands.", "Exit."]
        end = "Describe commitments or ask general questions in English or Spanish; commands keep the last language.\nGeneral answers are not verified personal-data results. No background reminders or automatic scheduling yet."
    else:
        intro = "Comandos (también disponibles sin IA):"
        descriptions = ["Mostrar compromisos pendientes y completados.", "Proponer cambios; null elimina una fecha.",
                        "Proponer completar un compromiso.", "Aplicar exactamente la propuesta mostrada.",
                        "Descartar propuesta y aclaraciones.", "Mostrar comandos.", "Salir."]
        end = "Describe compromisos o haz preguntas generales en español o inglés; los comandos conservan el último idioma.\nLas respuestas generales no son resultados verificados sobre tus datos. Todavía no hay recordatorios ni planificación automática."
    commands = ["/list [university|work|personal] [--all]", '/edit ID {"due_date":"2026-11-24"}',
                "/done ID", "/confirm", "/cancel", "/help", "/quit"]
    lines = [intro, '  /new {"title":"Report","area":"university","due_date":"2026-11-23"}']
    lines.extend(f"  {command} — {description}" for command, description in zip(commands, descriptions))
    fields = ("Fields" if language == "en" else "Campos") + ": title, area, project, due_date (YYYY-MM-DD | null)."
    scope = ("Default: last 7 days onward, plus older overdue and undated pending; --all includes full history."
             if language == "en" else
             "Por defecto: últimos 7 días en adelante, más vencidos anteriores y pendientes sin fecha; --all incluye todo el historial.")
    return "\n".join([*lines, fields, scope, end])


def deadline(value, language):
    if value is None:
        return text("no_date", language)
    parsed = date.fromisoformat(value)
    months = ("January February March April May June July August September October November December" if language == "en"
              else "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre").split()
    month = months[parsed.month - 1]
    if language == "es":
        return f"{parsed.day} de {month} de {parsed.year}"
    return f"{month} {parsed.day}, {parsed.year}"


def records(rows, language):
    if not rows:
        return text("empty", language)
    blocks = []
    for row in rows:
        lines = [display_value(row["title"])]
        if "id" in row:
            lines.append(f"ID: {row['id']}")
        lines.append(f"{text('area', language)}: {text(row['area'], language)}")
        if row.get("project"):
            lines.append(f"{text('project', language)}: {display_value(row['project'])}")
        lines.append(f"{text('due', language)}: {deadline(row.get('due_date'), language)}")
        if "status" in row:
            status = "pending_status" if row["status"] == "pending" else "completed"
            lines.append(f"{text('status', language)}: {text(status, language)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def display_value(value):
    """Keep user/model fields on one line without terminal control sequences."""
    return "".join(char if char.isprintable() else f"\\u{ord(char):04x}" for char in value)


def general_reply(answer, language):
    body = "\n".join(display_value(line) for line in answer.strip().split("\n"))
    return text("general_reply", language) + "\n" + body


def query_records(result, language):
    area = text(result["area"], language) if result["area"] else text("all_areas", language)
    if result["scope"] == "all":
        heading = text("history", language)
    elif result["scope"] == "range":
        heading = f"{deadline(result['start_date'], language)} → {deadline(result['end_date'], language)}"
    else:
        start = deadline(result["start_date"], language)
        heading = f"From {start} onward" if language == "en" else f"Desde {start} en adelante"
    heading += f" · {area}"
    rows = result["rows"]
    if not rows:
        return heading + "\n" + text("empty_scope", language)
    if result["scope"] != "current":
        return heading + "\n" + records(rows, language)
    groups = {
        "recent": [row for row in rows if row["due_date"] is not None and row["due_date"] >= result["start_date"]],
        "overdue": [row for row in rows if row["due_date"] is not None and row["due_date"] < result["start_date"]],
        "undated": [row for row in rows if row["due_date"] is None],
    }
    return "\n\n".join([heading, *[text(key, language) + "\n" + records(group, language)
                                    for key, group in groups.items() if group]])


def proposal(value, language):
    if value["action"] == "create":
        rows = value["items"]
    else:
        row = dict(value["before"])
        row.update(value.get("fields", {}))
        if value["action"] == "complete":
            row["status"] = "completed"
        rows = [row]
    return "\n".join([text("proposal", language), text(value["action"], language),
                      records(rows, language), text("confirm", language)])


def runtime_message(status, model, language):
    if language == "en":
        return status.message
    if status.ready:
        return f"Ollama disponible: {model}"
    messages = {
        "Planner requires loopback HTTP Ollama on port 11434; no connection made.":
            "El organizador requiere Ollama local por HTTP en el puerto 11434. No se realizó ninguna conexión.",
        "Startup wait must be between 0 and 120 seconds.": "La espera de inicio debe estar entre 0 y 120 segundos.",
        "Ollama unavailable; autostart is disabled. Offline commands remain available.":
            "Ollama no está disponible y el autoarranque está desactivado. Los comandos sin IA siguen disponibles.",
        f"Model {model} is not installed. Download it manually; no download attempted.":
            f"El modelo {model} no está instalado. Descárgalo manualmente; no se intentó descargar nada.",
        "Could not launch ollama serve. Check installation and permissions.":
            "No se pudo iniciar ollama serve. Revisa la instalación y los permisos.",
        "ollama serve exited before becoming ready. Check the configured service.":
            "ollama serve terminó antes de estar disponible. Revisa el servicio configurado.",
        "Ollama startup timed out. Offline commands remain available.":
            "Se agotó la espera de inicio de Ollama. Los comandos sin IA siguen disponibles.",
    }
    return messages.get(status.message, text("offline", language))
