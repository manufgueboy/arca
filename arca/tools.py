"""Herramientas del agente: archivos, terminal, Mac, Chrome, web y skills.

Cada herramienta se registra con @tool. `riesgo=True` significa que Arca pide
confirmación antes de ejecutarla (salvo que actives auto-aprobar).
"""
from __future__ import annotations

import html
import json
import os
import platform
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from . import skills as skillsmod

ES_MAC = platform.system() == "Darwin"
LIMITE = 20000


class Tool:
    def __init__(self, fn: Callable, descripcion: str, params: dict, requeridos: list[str],
                 riesgo, grupo: str = "base", nombre: str | None = None):
        self.fn, self.nombre, self.grupo = fn, nombre or fn.__name__, grupo
        self._riesgo = riesgo
        self.esquema = {"type": "function", "function": {
            "name": self.nombre, "description": descripcion,
            "parameters": {"type": "object", "properties": params, "required": requeridos}}}


    def es_riesgosa(self, args: dict) -> bool:
        return bool(self._riesgo(args) if callable(self._riesgo) else self._riesgo)


REGISTRO: dict[str, Tool] = {}


def tool(descripcion: str = "", riesgo=False, grupo: str = "base", **params: str):
    """Registra una herramienta. params: nombre=descripcion (sufijo '?' = opcional)."""
    def deco(fn):
        props, req = {}, []
        for k, d in params.items():
            opcional = d.endswith("?")
            props[k] = {"type": "string", "description": d.rstrip("?")}
            if not opcional:
                req.append(k)
        REGISTRO[fn.__name__] = Tool(fn, descripcion, props, req, riesgo, grupo)
        return fn
    return deco


def _cortar(s: str) -> str:
    return s if len(s) <= LIMITE else s[:LIMITE] + f"\n[…truncado, {len(s)} caracteres en total]"


def limitar(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f"\n[…recortado: {len(s)} caracteres en total]"


def _ruta(p: str) -> Path:
    return Path(p).expanduser().resolve()


# ─────────────────────────── Archivos y terminal ───────────────────────────

@tool("Lee un archivo de texto.", ruta="Ruta del archivo (acepta ~)")
def leer_archivo(ruta: str) -> str:
    p = _ruta(ruta)
    if not p.is_file():
        return f"[error] No existe: {p}"
    return _cortar(p.read_text(encoding="utf-8", errors="replace"))


@tool("Crea o sobrescribe un archivo de texto.", riesgo=True,
      ruta="Ruta del archivo", contenido="Contenido completo")
def escribir_archivo(ruta: str, contenido: str) -> str:
    p = _ruta(ruta)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenido, encoding="utf-8")
    return f"[ok] Guardado {p} ({len(contenido)} caracteres)"


@tool("Lista el contenido de una carpeta.", ruta="Carpeta (por default la actual)?")
def listar_carpeta(ruta: str = ".") -> str:
    p = _ruta(ruta)
    if not p.is_dir():
        return f"[error] No es carpeta: {p}"
    items = [f"{x.name}/" if x.is_dir() else x.name for x in sorted(p.iterdir()) if not x.name.startswith(".")]
    return _cortar("\n".join(items) or "(vacía)")


@tool("Ejecuta un comando en la terminal (zsh/bash) y devuelve la salida.", riesgo=True,
      comando="Comando a ejecutar")
def terminal(comando: str) -> str:
    try:
        r = subprocess.run(comando, shell=True, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "[error] Tiempo agotado (180 s)"
    salida = (r.stdout or "") + (r.stderr or "")
    return _cortar(salida.strip() or f"(sin salida, código {r.returncode})")


# ─────────────────────────────── Mac ───────────────────────────────────────

def _osascript(script: str, *args: str) -> str:
    if not ES_MAC:
        return "[error] Esta herramienta solo funciona en macOS."
    r = subprocess.run(["osascript", "-e", script, *args], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return f"[error] {r.stderr.strip()}"
    return r.stdout.strip() or "[ok]"


@tool(grupo="mac", descripcion="Ejecuta AppleScript para controlar la Mac y sus apps (Finder, Mail, Notas, Música, "
      "Calendario, Recordatorios, System Events, etc.). Úsalo solo si no hay una herramienta específica.",
      riesgo=True, script="Código AppleScript")
def applescript(script: str) -> str:
    return _cortar(_osascript(script))


@tool("Abre una app, archivo, carpeta o URL en la Mac (como el comando `open`).", riesgo=True,
      que="Nombre de app (ej. 'Safari'), ruta o URL")
def abrir(que: str) -> str:
    if not ES_MAC:
        return "[error] Solo en macOS."
    es_ruta_o_url = "/" in que or "://" in que or que.startswith("~")
    cmd = ["open", str(_ruta(que)) if que.startswith("~") else que] if es_ruta_o_url else ["open", "-a", que]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return "[ok]" if r.returncode == 0 else f"[error] {r.stderr.strip()}"


@tool(grupo="mac", descripcion="Muestra una notificación en la Mac.", titulo="Título", mensaje="Texto")
def notificar(titulo: str, mensaje: str) -> str:
    return _osascript("on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run",
                      titulo, mensaje)


# ─────────────────────────────── Chrome ────────────────────────────────────
# Usa AppleScript sobre tu Chrome real (con tus sesiones). Para leer/clic/escribir
# hay que activar una vez: Chrome > Ver > Opciones para desarrolladores >
# "Permitir JavaScript de eventos de Apple".

_AVISO_JS = ("[error] Chrome no permite JavaScript desde AppleScript. Actívalo una vez en Chrome: "
             "menú Ver > Opciones para desarrolladores > 'Permitir JavaScript de eventos de Apple'.")


def _chrome_js(js: str) -> str:
    out = _osascript('on run argv\ntell application "Google Chrome" to execute front window\'s '
                     'active tab javascript (item 1 of argv)\nend run', js)
    if out.startswith("[error]") and ("JavaScript" in out or "-1723" in out or "-2700" in out):
        return _AVISO_JS
    return out


@tool(grupo="chrome", descripcion="Abre una URL en Google Chrome (pestaña nueva) y espera a que cargue.", riesgo=True, url="URL")
def chrome_abrir(url: str) -> str:
    if "://" not in url:
        url = "https://" + url
    out = _osascript('on run argv\ntell application "Google Chrome"\nactivate\n'
                     'if (count of windows) = 0 then make new window\n'
                     'tell front window to make new tab with properties {URL:(item 1 of argv)}\n'
                     'end tell\nend run', url)
    for _ in range(30):
        time.sleep(0.5)
        if _osascript('tell application "Google Chrome" to get loading of active tab of front window') == "false":
            break
    return out if out.startswith("[error]") else f"[ok] Abierto {url}"


@tool(grupo="chrome", descripcion="Lista las pestañas abiertas en Chrome (título y URL).")
def chrome_pestanas() -> str:
    return _osascript('set salida to ""\ntell application "Google Chrome"\n'
                      'repeat with w in windows\nrepeat with t in tabs of w\n'
                      'set salida to salida & (title of t) & " | " & (URL of t) & linefeed\n'
                      'end repeat\nend repeat\nend tell\nreturn salida')


@tool(grupo="chrome", descripcion="Lee el texto de la pestaña activa de Chrome, con la lista de links y botones visibles.")
def chrome_leer() -> str:
    js = r"""(() => {
      const els = [...document.querySelectorAll('a,button,input,textarea,select,[role=button]')]
        .filter(e => e.offsetParent !== null).slice(0, 150)
        .map((e, i) => `[${i}] <${e.tagName.toLowerCase()}> ` +
             (e.innerText || e.value || e.placeholder || e.getAttribute('aria-label') || e.name || '').trim().slice(0, 80));
      return 'TÍTULO: ' + document.title + '\nURL: ' + location.href + '\n\n' +
             document.body.innerText.slice(0, 15000) + '\n\nELEMENTOS INTERACTIVOS:\n' + els.join('\n');
    })()"""
    return _cortar(_chrome_js(js))


@tool(grupo="chrome", descripcion="Da clic en un elemento de la pestaña activa de Chrome. Usa el número [i] que da chrome_leer, "
      "o un texto visible, o un selector CSS.", riesgo=True, objetivo="Número, texto visible o selector CSS")
def chrome_clic(objetivo: str) -> str:
    js = """((o) => {
      const vis = [...document.querySelectorAll('a,button,input,textarea,select,[role=button]')]
        .filter(e => e.offsetParent !== null).slice(0, 150);
      let el = /^\\d+$/.test(o) ? vis[+o] : null;
      if (!el) { try { el = document.querySelector(o); } catch (e) {} }
      if (!el) el = vis.find(e => (e.innerText || e.value || '').trim().toLowerCase().includes(o.toLowerCase()));
      if (!el) return 'No encontré: ' + o;
      el.scrollIntoView({block: 'center'}); el.click();
      return 'Clic en <' + el.tagName.toLowerCase() + '> ' + (el.innerText || el.value || '').trim().slice(0, 60);
    })(%s)""" % json.dumps(objetivo)
    out = _chrome_js(js)
    time.sleep(1)
    return out


@tool(grupo="chrome", descripcion="Escribe texto en un campo de la pestaña activa de Chrome.", riesgo=True,
      objetivo="Número [i] de chrome_leer, selector CSS o placeholder", texto="Texto a escribir",
      enviar="'si' para presionar Enter / enviar el formulario después?")
def chrome_escribir(objetivo: str, texto: str, enviar: str = "no") -> str:
    js = """((o, t, env) => {
      const vis = [...document.querySelectorAll('a,button,input,textarea,select,[role=button]')]
        .filter(e => e.offsetParent !== null).slice(0, 150);
      let el = /^\\d+$/.test(o) ? vis[+o] : null;
      if (!el) { try { el = document.querySelector(o); } catch (e) {} }
      if (!el) el = [...document.querySelectorAll('input,textarea')].find(e => (e.placeholder || e.name || '').toLowerCase().includes(o.toLowerCase()));
      if (!el) return 'No encontré el campo: ' + o;
      el.focus();
      const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
      if (setter && setter.set) setter.set.call(el, t); else el.value = t;
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      if (env) {
        el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
        if (el.form) (el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit());
      }
      return 'Escrito en <' + el.tagName.toLowerCase() + '>' + (env ? ' y enviado' : '');
    })(%s, %s, %s)""" % (json.dumps(objetivo), json.dumps(texto), "true" if enviar.lower().startswith("s") else "false")
    return _chrome_js(js)


@tool(grupo="chrome_avanzado", descripcion="Ejecuta JavaScript en la pestaña activa de Chrome y devuelve el resultado.", riesgo=True,
      codigo="Expresión JavaScript")
def chrome_js(codigo: str) -> str:
    return _cortar(_chrome_js(codigo))


# ─────────────────────────────── Web ───────────────────────────────────────

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def _get(url: str, datos: dict | None = None) -> str:
    body = urllib.parse.urlencode(datos).encode() if datos else None
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": _UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def _html_a_texto(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|noscript|svg|head).*?</\1>", " ", h)
    h = re.sub(r"(?i)<(br|/p|/div|/li|/h\d|/tr)>", "\n", h)
    h = html.unescape(re.sub(r"<[^>]+>", " ", h))
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", h)).strip()


@tool(grupo="web", descripcion="Busca en internet (DuckDuckGo) y devuelve títulos, links y resúmenes.", consulta="Qué buscar")
def buscar_web(consulta: str) -> str:
    res = []
    try:
        h = _get("https://html.duckduckgo.com/html/", {"q": consulta})
        titulos = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', h, re.S) or \
            [(u, t) for t, u in re.findall(r'href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>', h, re.S)]
        resumenes = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>', h, re.S)
        if not titulos:  # respaldo: versión lite
            h = _get("https://lite.duckduckgo.com/lite/", {"q": consulta})
            titulos = re.findall(r"href=\"([^\"]+)\"[^>]*class='result-link'>(.*?)</a>", h, re.S)
            resumenes = re.findall(r"class='result-snippet'>(.*?)</td>", h, re.S)
    except Exception as e:
        return f"[error] {e}"
    for i, (link, titulo) in enumerate(titulos[:8]):
        if "uddg=" in link:
            link = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])
        if link.startswith("//"):
            link = "https:" + link
        resumen = _html_a_texto(resumenes[i]) if i < len(resumenes) else ""
        res.append((_html_a_texto(titulo), link, resumen))
    if not res:
        return "(sin resultados)"
    salida = "\n".join(f"- {t}\n  {l}\n  {r}" for t, l, r in res)
    # Para que un modelo chico no tenga que decidir qué leer: traemos el texto de los 2 primeros.
    leidos = 0
    for t, l, _ in res:
        if leidos >= 2:
            break
        try:
            texto = _html_a_texto(_get(l))
        except Exception:
            continue
        if len(texto) > 200:
            salida += f"\n\n=== Contenido de {l} ===\n{_extracto(texto, consulta)}"
            leidos += 1
    return salida


def _extracto(texto: str, consulta: str, n: int = 2500) -> str:
    """Las partes del texto que más coinciden con la búsqueda (no solo el inicio de la página)."""
    palabras = [w for w in re.findall(r"\w{3,}", consulta.lower())]
    parrafos = [p.strip() for p in re.split(r"\n\s*\n|\n", texto) if len(p.strip()) > 30]
    puntuados = sorted(range(len(parrafos)), key=lambda i: -sum(w in parrafos[i].lower() for w in palabras))
    elegidos = sorted(puntuados[:12])
    out = "\n".join(parrafos[i] for i in elegidos)
    return out[:n]


@tool(grupo="web", descripcion="Descarga una página web y devuelve su texto (sin abrir Chrome).", url="URL")
def leer_web(url: str) -> str:
    try:
        return _cortar(_html_a_texto(_get(url if "://" in url else "https://" + url)))
    except Exception as e:
        return f"[error] {e}"



# ──────────────────── Acciones de alto nivel (el código hace el trabajo) ────────────────────
# Pensadas para modelos chicos: en vez de escribir AppleScript de memoria, solo llenan datos.

def _fecha_as(fecha: str) -> str:
    """'2026-09-25 17:00' → bloque AppleScript que arma la fecha (sin depender del idioma de la Mac)."""
    import datetime as _dt
    fecha = fecha.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = _dt.datetime.strptime(fecha, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Fecha inválida '{fecha}'. Usa el formato AAAA-MM-DD HH:MM, ej. 2026-09-25 17:00")
    return (f"set d to current date\nset day of d to 1\nset year of d to {d.year}\nset month of d to {d.month}\n"
            f"set day of d to {d.day}\nset hours of d to {d.hour}\nset minutes of d to {d.minute}\nset seconds of d to 0\n")


@tool(grupo="mac", descripcion="Crea un recordatorio en la app Recordatorios de la Mac.", riesgo=False,
      texto="Qué recordar", fecha="Cuándo avisar, formato AAAA-MM-DD HH:MM (opcional)?")
def crear_recordatorio(texto: str, fecha: str = "") -> str:
    if fecha:
        script = _fecha_as(fecha) + 'tell application "Reminders" to make new reminder with properties {name:(item 1 of argv), remind me date:d}'
    else:
        script = 'tell application "Reminders" to make new reminder with properties {name:(item 1 of argv)}'
    out = _osascript("on run argv\n" + script + "\nend run", texto)
    return out if out.startswith("[error]") else f"[ok] Recordatorio creado: «{texto}»" + (f" para {fecha}" if fecha else "")


@tool(grupo="mac", descripcion="Crea un evento en la app Calendario de la Mac.", riesgo=False,
      titulo="Título del evento", inicio="Inicio, formato AAAA-MM-DD HH:MM",
      duracion_min="Duración en minutos (default 60)?", lugar="Lugar (opcional)?")
def crear_evento(titulo: str, inicio: str, duracion_min: str = "60", lugar: str = "") -> str:
    try:
        dur = int(float(duracion_min or 60))
    except ValueError:
        dur = 60
    script = (_fecha_as(inicio) +
              'tell application "Calendar"\n'
              'set cal to first calendar whose writable is true\n'
              f'tell cal to make new event with properties {{summary:(item 1 of argv), start date:d, end date:(d + {dur * 60}), location:(item 2 of argv)}}\n'
              'end tell')
    out = _osascript("on run argv\n" + script + "\nend run", titulo, lugar)
    return out if out.startswith("[error]") else f"[ok] Evento «{titulo}» el {inicio} ({dur} min)"


@tool(grupo="mac", descripcion="Abre un borrador de correo en la app Mail, listo para que el usuario lo revise y envíe. NO lo envía.",
      para="Correo del destinatario (opcional)?", asunto="Asunto", cuerpo="Texto del correo")
def borrador_correo(asunto: str, cuerpo: str, para: str = "") -> str:
    script = ('on run argv\ntell application "Mail"\n'
              'set m to make new outgoing message with properties {subject:(item 1 of argv), content:(item 2 of argv), visible:true}\n'
              'if (item 3 of argv) is not "" then\n'
              'tell m to make new to recipient at end of to recipients with properties {address:(item 3 of argv)}\n'
              'end if\nactivate\nend tell\nend run')
    out = _osascript(script, asunto, cuerpo, para)
    return out if out.startswith("[error]") else "[ok] Borrador abierto en Mail (no se envió)."


_TIPOS = {
    "Imágenes": {"jpg", "jpeg", "png", "gif", "heic", "webp", "svg", "bmp", "tiff", "raw"},
    "Documentos": {"pdf", "doc", "docx", "pages", "txt", "md", "rtf", "odt", "epub"},
    "Hojas de cálculo": {"xls", "xlsx", "csv", "numbers", "ods"},
    "Presentaciones": {"ppt", "pptx", "key", "odp"},
    "Videos": {"mp4", "mov", "mkv", "avi", "m4v", "webm"},
    "Audio": {"mp3", "wav", "m4a", "aac", "flac", "ogg"},
    "Instaladores y comprimidos": {"dmg", "pkg", "zip", "rar", "7z", "tar", "gz", "iso"},
}


@tool(grupo="archivos", descripcion="Ordena una carpeta moviendo sus archivos a subcarpetas por tipo "
      "(Imágenes, Documentos, Videos…). Con aplicar='no' solo muestra el plan; con aplicar='si' lo hace. Nunca borra ni sobrescribe.",
      riesgo=lambda a: str(a.get("aplicar", "no")).lower().startswith("s"),
      ruta="Nombre o ruta EXACTA de la carpeta que dijo el usuario, ej. 'fotos' o '~/Downloads'. No uses '.'",
      aplicar="'si' para mover de verdad, 'no' para solo ver el plan")
def organizar_carpeta(ruta: str, aplicar: str = "no") -> str:
    if ruta.strip() in ("", ".", "./"):
        subs = [x.name for x in sorted(Path.cwd().iterdir()) if x.is_dir() and not x.name.startswith(".")][:15]
        return ("[error] Falta el nombre de la carpeta. '.' es la carpeta actual (" + str(Path.cwd()) + "). "
                "Usa el nombre exacto que dijo el usuario" + (f"; aquí hay estas subcarpetas: {', '.join(subs)}" if subs else "")
                + ". Si de verdad quiere la carpeta actual, usa su ruta completa.")
    p = _ruta(ruta)
    if not p.is_dir():
        return f"[error] No es carpeta: {p}. Revisa el nombre con listar_carpeta."
    protegidas = {Path("/"), Path.home(), Path("/Applications"), Path("/System"), Path("/Library"), Path("/Users"),
                  Path.home() / "Library", Path.home() / "Applications"}
    if p in {x.resolve() for x in protegidas if x.exists()} or str(p).startswith(("/System", "/Library", "/usr", "/bin", "/private/var")):
        return f"[error] Por seguridad no organizo {p}. Elige una carpeta concreta, como ~/Downloads."
    plan: dict[str, list[Path]] = {}
    for f in sorted(p.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            ext = f.suffix.lower().lstrip(".")
            cat = next((c for c, exts in _TIPOS.items() if ext in exts), "Otros")
            plan.setdefault(cat, []).append(f)
    if not plan:
        return "La carpeta no tiene archivos sueltos que ordenar."
    resumen = "\n".join(f"- {c}: {len(fs)} ({', '.join(x.name for x in fs[:4])}{'…' if len(fs) > 4 else ''})"
                        for c, fs in plan.items())
    if not str(aplicar).lower().startswith("s"):
        return f"PLAN para {p} (nada se ha movido todavía):\n{resumen}"
    movidos = 0
    for c, fs in plan.items():
        (p / c).mkdir(exist_ok=True)
        for f in fs:
            destino = p / c / f.name
            if not destino.exists():
                f.rename(destino)
                movidos += 1
    return f"[ok] Moví {movidos} archivos en {p}:\n{resumen}"


@tool(grupo="web", descripcion="Busca en Wikipedia y devuelve el resumen del artículo. Úsalo para datos, definiciones, personas, lugares e historia.",
      consulta="Qué buscar", idioma="Código de idioma, default 'es'?")
def wikipedia(consulta: str, idioma: str = "es") -> str:
    base = f"https://{idioma or 'es'}.wikipedia.org"
    try:
        r = json.loads(_get(f"{base}/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch="
                            + urllib.parse.quote(consulta)))
        hits = r.get("query", {}).get("search", [])
        if not hits:
            return "(sin resultados en Wikipedia)"
        titulo = hits[0]["title"]
        s = json.loads(_get(f"{base}/api/rest_v1/page/summary/" + urllib.parse.quote(titulo.replace(" ", "_"))))
        otros = ", ".join(h["title"] for h in hits[1:])
        return (f"{s.get('title', titulo)}\n{s.get('extract', '')}\nFuente: {base}/wiki/{urllib.parse.quote(titulo.replace(' ', '_'))}"
                + (f"\nOtros artículos: {otros}" if otros else ""))
    except Exception as e:
        return f"[error] {e}"


@tool(grupo="mac", descripcion="Datos actuales de la Mac: batería, Wi-Fi, disco, memoria, apps abiertas.")
def info_mac() -> str:
    partes = []
    for titulo, cmd in (("Batería", "pmset -g batt | tail -1"),
                        ("Disco", "df -h ~ | tail -1 | awk '{print $4\" libres de \"$2}'"),
                        ("Memoria", "memory_pressure 2>/dev/null | tail -1"),
                        ("Wi-Fi", "networksetup -getairportnetwork en0 2>/dev/null"),
                        ("Encendida desde", "uptime")):
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
        if r:
            partes.append(f"{titulo}: {r}")
    apps = _osascript('tell application "System Events" to get name of (processes where background only is false)')
    if not apps.startswith("[error]"):
        partes.append(f"Apps abiertas: {apps}")
    return "\n".join(partes)


# ─────────────────────────────── Skills ────────────────────────────────────

@tool(grupo="skills", descripcion="Carga las instrucciones de una skill instalada. Hazlo ANTES de una tarea que coincida "
      "con la descripción de alguna skill.", nombre="Nombre de la skill")
def usar_skill(nombre: str) -> str:
    s = skillsmod.cargar().get(nombre)
    if not s:
        return f"[error] No existe '{nombre}'. Disponibles: {', '.join(skillsmod.cargar()) or 'ninguna'}"
    extras = [str(p.relative_to(s.path)) for p in s.path.rglob("*") if p.is_file() and p.name != "SKILL.md"]
    pie = f"\n\n(Archivos de apoyo en {s.path}: {', '.join(extras)})" if extras else ""
    return f"# Skill: {s.nombre}\n\n{s.cuerpo}{pie}"


# ─────────────────────────────── API ───────────────────────────────────────

def _registrar_skills_ejecutables() -> None:
    """Una skill con tool.json se vuelve herramienta: el modelo solo llena parámetros y Arca ejecuta el script."""
    for nombre in [n for n, t in REGISTRO.items() if t.grupo == "skill_ejecutable"]:
        del REGISTRO[nombre]
    for s in skillsmod.cargar().values():
        spec_path = s.path / "tool.json"
        if not spec_path.is_file():
            continue
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        nombre = spec.get("nombre") or s.nombre.replace("-", "_")
        params = {k: {"type": "string", "description": v.rstrip("?")} for k, v in spec.get("parametros", {}).items()}
        req = [k for k, v in spec.get("parametros", {}).items() if not v.endswith("?")]

        def correr(_dir=s.path, _cmd=spec["ejecutar"], **args):
            env = {**os.environ, **{f"ARCA_{k.upper()}": str(v) for k, v in args.items()}}
            r = subprocess.run(_cmd, shell=True, cwd=_dir, input=json.dumps(args), capture_output=True,
                               text=True, timeout=int(spec.get("timeout", 120)), env=env)
            return _cortar(((r.stdout or "") + (r.stderr or "")).strip() or f"(sin salida, código {r.returncode})")

        t = Tool(correr, spec.get("descripcion", s.descripcion), params, req, bool(spec.get("riesgo", False)),
                 "skill_ejecutable", nombre)
        REGISTRO[nombre] = t


# Palabras que activan cada grupo de herramientas (para modelos chicos: menos opciones = menos errores).
GRUPOS_PALABRAS = {
    "web": ("busca", "investiga", "internet", "web", "google", "noticia", "qué es", "que es", "quién", "quien",
            "cuándo", "cuando", "dónde", "donde", "cuánto", "cuanto", "precio", "cuesta", "versión", "version",
            "último", "ultimo", "última", "ultima", "actual", "wikipedia", "información", "informacion",
            "dato", "historia", "significa", "define", "explica", "clima", "tiempo", "temperatura", "?", "¿"),
    "chrome": ("chrome", "navegador", "pestaña", "pestana", "página", "pagina", "sitio", ".com", "http", "www",
               "youtube", "gmail", "clic", "click", "formulario", "inicia sesión", "login", "abierto en", "tengo abierto"),
    "mac": ("recuérdame", "recuerdame", "recordatorio", "calendario", "evento", "agenda", "cita", "reunión",
            "reunion", "correo", "mail", "email", "notific", "avísame", "avisame", "nota", "música", "musica",
            "spotify", "finder", "volumen", "brillo", "batería", "bateria", "wifi", "wi-fi", "app", "aplicación",
            "aplicacion", "mac", "memoria", "procesos", "abiert"),
    "archivos": ("organiza", "ordena", "limpia", "acomoda", "descargas", "downloads", "escritorio", "desktop", "carpeta"),
}


def grupos_para(texto: str) -> set[str]:
    t = texto.lower()
    return {g for g, palabras in GRUPOS_PALABRAS.items() if any(p in t for p in palabras)}


def esquemas(grupos: set[str] | None = None) -> list[dict]:
    """Todos los esquemas (grupos=None) o solo base + grupos pedidos (+ skills)."""
    _registrar_skills_ejecutables()
    if grupos is None:
        return [t.esquema for t in REGISTRO.values()]
    activos = {"base", "skills", "skill_ejecutable"} | grupos
    return [t.esquema for t in REGISTRO.values() if t.grupo in activos]


def ejecutar(nombre: str, args: dict) -> str:
    t = REGISTRO.get(nombre)
    if not t:
        return f"[error] Herramienta desconocida: {nombre}. Válidas: {', '.join(REGISTRO)}"
    try:
        return str(t.fn(**args))
    except TypeError as e:
        return f"[error] Argumentos inválidos para {nombre}: {e}"
    except Exception as e:
        return f"[error] {nombre} falló: {e}"
