"""Herramientas del agente: archivos, terminal, Mac, Chrome, web y skills.

Cada herramienta se registra con @tool. `riesgo=True` significa que Arca pide
confirmación antes de ejecutarla (salvo que actives auto-aprobar).
"""
from __future__ import annotations

import html
import json
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
    def __init__(self, fn: Callable, descripcion: str, params: dict, requeridos: list[str], riesgo: bool):
        self.fn, self.nombre, self.riesgo = fn, fn.__name__, riesgo
        self.esquema = {"type": "function", "function": {
            "name": fn.__name__, "description": descripcion,
            "parameters": {"type": "object", "properties": params, "required": requeridos}}}


REGISTRO: dict[str, Tool] = {}


def tool(descripcion: str, riesgo: bool = False, **params: str):
    """Registra una herramienta. params: nombre=descripcion (sufijo '?' = opcional)."""
    def deco(fn):
        props, req = {}, []
        for k, d in params.items():
            opcional = d.endswith("?")
            props[k] = {"type": "string", "description": d.rstrip("?")}
            if not opcional:
                req.append(k)
        REGISTRO[fn.__name__] = Tool(fn, descripcion, props, req, riesgo)
        return fn
    return deco


def _cortar(s: str) -> str:
    return s if len(s) <= LIMITE else s[:LIMITE] + f"\n[…truncado, {len(s)} caracteres en total]"


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


@tool("Ejecuta AppleScript para controlar la Mac y sus apps (Finder, Mail, Notas, Música, "
      "Calendario, Recordatorios, System Events, etc.).", riesgo=True, script="Código AppleScript")
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


@tool("Muestra una notificación en la Mac.", titulo="Título", mensaje="Texto")
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


@tool("Abre una URL en Google Chrome (pestaña nueva) y espera a que cargue.", riesgo=True, url="URL")
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


@tool("Lista las pestañas abiertas en Chrome (título y URL).")
def chrome_pestanas() -> str:
    return _osascript('set salida to ""\ntell application "Google Chrome"\n'
                      'repeat with w in windows\nrepeat with t in tabs of w\n'
                      'set salida to salida & (title of t) & " | " & (URL of t) & linefeed\n'
                      'end repeat\nend repeat\nend tell\nreturn salida')


@tool("Lee el texto de la pestaña activa de Chrome, con la lista de links y botones visibles.")
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


@tool("Da clic en un elemento de la pestaña activa de Chrome. Usa el número [i] que da chrome_leer, "
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


@tool("Escribe texto en un campo de la pestaña activa de Chrome.", riesgo=True,
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


@tool("Ejecuta JavaScript en la pestaña activa de Chrome y devuelve el resultado.", riesgo=True,
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


@tool("Busca en internet (DuckDuckGo) y devuelve títulos, links y resúmenes.", consulta="Qué buscar")
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
        res.append(f"- {_html_a_texto(titulo)}\n  {link}\n  {resumen}")
    return "\n".join(res) or "(sin resultados)"


@tool("Descarga una página web y devuelve su texto (sin abrir Chrome).", url="URL")
def leer_web(url: str) -> str:
    try:
        return _cortar(_html_a_texto(_get(url if "://" in url else "https://" + url)))
    except Exception as e:
        return f"[error] {e}"


# ─────────────────────────────── Skills ────────────────────────────────────

@tool("Carga las instrucciones de una skill instalada. Hazlo ANTES de una tarea que coincida "
      "con la descripción de alguna skill.", nombre="Nombre de la skill")
def usar_skill(nombre: str) -> str:
    s = skillsmod.cargar().get(nombre)
    if not s:
        return f"[error] No existe '{nombre}'. Disponibles: {', '.join(skillsmod.cargar()) or 'ninguna'}"
    extras = [str(p.relative_to(s.path)) for p in s.path.rglob("*") if p.is_file() and p.name != "SKILL.md"]
    pie = f"\n\n(Archivos de apoyo en {s.path}: {', '.join(extras)})" if extras else ""
    return f"# Skill: {s.nombre}\n\n{s.cuerpo}{pie}"


# ─────────────────────────────── API ───────────────────────────────────────

def esquemas() -> list[dict]:
    return [t.esquema for t in REGISTRO.values()]


def ejecutar(nombre: str, args: dict) -> str:
    t = REGISTRO.get(nombre)
    if not t:
        return f"[error] Herramienta desconocida: {nombre}"
    try:
        return str(t.fn(**args))
    except TypeError as e:
        return f"[error] Argumentos inválidos para {nombre}: {e}"
    except Exception as e:
        return f"[error] {nombre} falló: {e}"
