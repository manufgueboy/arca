"""Arca en el navegador: chat local para quien no quiere tocar la terminal.

  arca web            abre http://127.0.0.1:8765 (si ya está corriendo, solo abre el navegador)

Seguridad: solo escucha en 127.0.0.1, valida el encabezado Host (anti DNS-rebinding) y exige un
token por sesión en cada POST (una página web ajena no puede mandarle órdenes a Arca).
"""
from __future__ import annotations

import json
import secrets
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, config, equipo, providers, skills, tools
from .agent import Agente

PUERTO = 8765

NOMBRES = {
    "leer_archivo": "Leyendo archivo", "escribir_archivo": "Guardando archivo", "listar_carpeta": "Revisando carpeta",
    "terminal": "Ejecutando comando", "applescript": "Controlando la Mac", "abrir": "Abriendo",
    "notificar": "Enviando notificación", "chrome_abrir": "Abriendo página en Chrome",
    "chrome_pestanas": "Revisando pestañas de Chrome", "chrome_leer": "Leyendo la página",
    "chrome_clic": "Dando clic", "chrome_escribir": "Escribiendo en la página", "chrome_js": "Ejecutando código en Chrome",
    "buscar_web": "Buscando en internet", "leer_web": "Leyendo página web", "wikipedia": "Consultando Wikipedia",
    "usar_skill": "Cargando skill", "crear_recordatorio": "Creando recordatorio", "crear_evento": "Creando evento",
    "borrador_correo": "Preparando correo", "organizar_carpeta": "Organizando carpeta", "info_mac": "Revisando la Mac",
    "clima": "Consultando el clima",
}

LLAVES = {
    "groq": ("Groq", "https://console.groq.com/keys", "Muy rápido. Crea tu cuenta gratis y copia tu API key."),
    "openrouter": ("OpenRouter", "https://openrouter.ai/keys", "Muchos modelos gratis. Crea tu cuenta y copia tu API key."),
    "gemini": ("Google Gemini", "https://aistudio.google.com/apikey", "Entra con tu cuenta de Google y copia tu API key."),
    "openai": ("OpenAI", "https://platform.openai.com/api-keys", "De pago por uso."),
    "anthropic": ("Claude (Anthropic)", "https://console.anthropic.com/settings/keys", "De pago por uso."),
}


class Estado:
    def __init__(self):
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(24)
        self.cfg = config.cargar()
        self.agente: Agente | None = None
        self.error_modelo = ""
        self.eventos: list[dict] = []
        self.ocupado = False
        self.auto = bool(self.cfg.get("auto_aprobar"))
        self.pendiente: dict | None = None
        self.descarga = {"activa": False, "texto": "", "pct": 0.0, "error": ""}
        self.servidor: ThreadingHTTPServer | None = None
        self.cargar_modelo()

    # ── modelo ────────────────────────────────────────────────────────────
    def cargar_modelo(self, proveedor: str | None = None, modelo: str | None = None) -> None:
        try:
            if (proveedor or self.cfg["proveedor"]) == "ollama":
                if equipo.ollama_instalado() and not equipo.ollama_corriendo():
                    equipo.iniciar_ollama()          # tras reiniciar la Mac, Ollama suele estar apagado
            if (proveedor or self.cfg["proveedor"]) == "ollama" and not modelo and not self.cfg.get("modelo"):
                if not equipo.modelos_locales():
                    raise providers.ProveedorError("Aún no hay un modelo descargado.")
            prov = providers.crear(self.cfg, proveedor, modelo)
            historial = self.agente.historial if self.agente else []
            self.agente = Agente(prov, self.cfg.get("max_pasos", 30), self.confirmar, self.mostrar,
                                 self.resultado, self.cfg.get("modo", "auto"))
            self.agente.historial = historial
            self.error_modelo = ""
            if proveedor:
                self.cfg["proveedor"], self.cfg["modelo"] = prov.nombre, prov.modelo
                config.guardar(self.cfg)
        except providers.ProveedorError as e:
            self.agente, self.error_modelo = None, str(e)

    # ── eventos ───────────────────────────────────────────────────────────
    def evento(self, tipo: str, **datos) -> dict:
        with self.lock:
            ev = {"id": len(self.eventos), "tipo": tipo, **datos}
            self.eventos.append(ev)
            return ev

    def mostrar(self, nombre: str, args: dict) -> None:
        self.evento("herramienta", nombre=nombre, texto=NOMBRES.get(nombre, nombre),
                    args={k: str(v)[:300] for k, v in args.items()})

    def resultado(self, nombre: str, salida: str) -> None:
        self.evento("resultado", nombre=nombre, salida=salida[:1500])

    def confirmar(self, nombre: str, args: dict) -> bool:
        if self.auto:
            return True
        if nombre == "organizar_carpeta":
            detalle = tools.organizar_carpeta(args.get("ruta", "."), "no")
        else:
            detalle = args.get("comando") or args.get("script") or args.get("codigo") or \
                "\n".join(f"{k}: {v}" for k, v in args.items())
        esperar = threading.Event()
        ev = self.evento("confirmar", nombre=nombre, texto=NOMBRES.get(nombre, nombre), detalle=str(detalle)[:3000])
        self.pendiente = {"id": ev["id"], "espera": esperar, "respuesta": False}
        esperar.wait()
        r = self.pendiente["respuesta"] if self.pendiente else False
        self.pendiente = None
        self.evento("confirmado", ref=ev["id"], si=bool(r))
        return bool(r)

    def responder_confirmacion(self, respuesta: str) -> None:
        p = self.pendiente
        if not p:
            return
        if respuesta == "todo":
            self.auto = True
        p["respuesta"] = respuesta in ("si", "todo")
        p["espera"].set()

    # ── tareas ────────────────────────────────────────────────────────────
    def enviar(self, texto: str) -> bool:
        if self.ocupado or not self.agente:
            return False
        self.ocupado = True
        self.evento("usuario", texto=texto)

        def correr():
            t0 = time.time()
            try:
                r = self.agente.preguntar(texto)
                self.evento("respuesta", texto=r, seg=round(time.time() - t0, 1))
            except providers.ProveedorError as e:
                self.agente.reparar()
                self.evento("error", texto=str(e))
            except Exception as e:  # noqa: BLE001
                self.agente.reparar()
                self.evento("error", texto=f"Algo falló: {e}")
            finally:
                self.ocupado = False
        threading.Thread(target=correr, daemon=True).start()
        return True

    def detener(self) -> None:
        if self.agente:
            self.agente.cancelar()
        self.responder_confirmacion("no")

    def descargar(self, modelo: str) -> None:
        if self.descarga["activa"]:
            return
        self.descarga.update(activa=True, texto="Preparando…", pct=0.0, error="")

        def progreso(texto, pct):
            self.descarga["texto"] = texto
            if pct >= 0:
                self.descarga["pct"] = pct

        def correr():
            try:
                if not equipo.ollama_corriendo():
                    if not equipo.instalar_ollama(progreso):
                        raise RuntimeError("No pude iniciar Ollama. Ábrelo desde Aplicaciones y reintenta.")
                if modelo:
                    equipo.descargar_modelo(modelo, progreso)
                    self.cargar_modelo("ollama", modelo)
                self.descarga.update(texto="¡Listo!", pct=1.0)
            except Exception as e:  # noqa: BLE001
                self.descarga["error"] = str(e)
            finally:
                self.descarga["activa"] = False
        threading.Thread(target=correr, daemon=True).start()

    def estado(self) -> dict:
        ram, libre = equipo.ram_gb(), equipo.disco_libre_gb()
        rec = equipo.recomendar(ram, libre)
        locales = equipo.modelos_locales()
        ids_locales = {m["id"] for m in locales}
        catalogo = [{**m, "instalado": m["id"] in ids_locales, "cabe": m["ram_min"] <= ram and m["gb"] + 3 <= libre,
                     "recomendado": m["id"] == rec["id"]} for m in equipo.CATALOGO]
        nube = [{"id": k, "nombre": v[0], "url": v[1], "ayuda": v[2],
                 "tiene_key": bool(config.api_key(self.cfg, k, config.proveedores(self.cfg)[k]))}
                for k, v in LLAVES.items()]
        a = self.agente
        return {
            "version": __version__, "listo": a is not None, "error_modelo": self.error_modelo,
            "proveedor": a.prov.nombre if a else "", "modelo": a.prov.modelo if a else "",
            "compacto": bool(a and a.compacto), "local": bool(a and a.prov.nombre in ("ollama", "lmstudio")),
            "ram": ram, "disco": libre, "catalogo": catalogo, "locales": locales,
            "ollama": {"instalado": equipo.ollama_instalado(), "corriendo": equipo.ollama_corriendo()},
            "nube": nube, "ocupado": self.ocupado, "descarga": self.descarga, "auto": self.auto,
            "skills": [{"nombre": s.nombre, "descripcion": s.descripcion} for s in skills.cargar().values()],
        }


E: Estado | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "Arca"

    def log_message(self, *a):
        pass

    def _host_ok(self) -> bool:
        h = (self.headers.get("Host") or "").split(":")[0]
        return h in ("127.0.0.1", "localhost")

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "host"}, 403)
        ruta = self.path.split("?")[0]
        if ruta == "/":
            body = PAGINA.replace("__TOKEN__", E.token).replace("__VERSION__", __version__).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)
        elif ruta == "/api/ping":
            self._json({"arca": True})
        elif ruta == "/api/estado":
            self._json(E.estado())
        elif ruta == "/api/eventos":
            desde = int((self.path.split("desde=")[1:] or ["0"])[0].split("&")[0] or 0)
            self._json({"eventos": E.eventos[desde:], "ocupado": E.ocupado, "descarga": E.descarga})
        else:
            self._json({"error": "no encontrado"}, 404)

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Arca-Token") != E.token:
            return self._json({"error": "no autorizado"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            datos = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except json.JSONDecodeError:
            datos = {}
        ruta = self.path
        if ruta == "/api/mensaje":
            texto = str(datos.get("texto", "")).strip()
            if not texto:
                return self._json({"ok": False})
            return self._json({"ok": E.enviar(texto)}, 200)
        if ruta == "/api/confirmar":
            E.responder_confirmacion(datos.get("respuesta", "no"))
        elif ruta == "/api/detener":
            E.detener()
        elif ruta == "/api/nuevo":
            if E.agente and not E.ocupado:
                E.agente.nuevo()
            E.evento("nuevo")
        elif ruta == "/api/auto":
            E.auto = bool(datos.get("auto"))
        elif ruta == "/api/usar":
            E.cargar_modelo(datos.get("proveedor"), datos.get("modelo") or None)
            return self._json({"ok": E.agente is not None, "error": E.error_modelo})
        elif ruta == "/api/key":
            prov, key = datos.get("proveedor"), str(datos.get("key", "")).strip()
            if prov not in LLAVES or len(key) < 10:
                return self._json({"ok": False, "error": "Esa llave no parece válida."})
            E.cfg.setdefault("api_keys", {})[prov] = key
            config.guardar(E.cfg)
            E.cargar_modelo(prov, None)
            return self._json({"ok": E.agente is not None, "error": E.error_modelo})
        elif ruta == "/api/descargar":
            E.descargar(datos.get("modelo", ""))
        elif ruta == "/api/apagar":
            self._json({"ok": True})
            threading.Thread(target=E.servidor.shutdown, daemon=True).start()
            return
        else:
            return self._json({"error": "no encontrado"}, 404)
        self._json({"ok": True})


def ya_corre(puerto: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/ping", timeout=1) as r:
            return json.loads(r.read()).get("arca", False)
    except Exception:
        return False


def servir(puerto: int = PUERTO, abrir: bool = True) -> None:
    global E
    url = f"http://127.0.0.1:{puerto}/"
    if ya_corre(puerto):
        if abrir:
            webbrowser.open(url)
        print(f"Arca ya está abierta en {url}")
        return
    import os
    os.chdir(Path.home())   # abierta desde el Dock arrancaría en "/": las rutas relativas deben ser desde ~
    E = Estado()
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Handler)
    srv.daemon_threads = True
    E.servidor = srv
    print(f"⛵ Arca en {url}  (Ctrl-C para cerrar)")
    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


PAGINA = (Path(__file__).parent / "web.html").read_text(encoding="utf-8") if (Path(__file__).parent / "web.html").exists() else ""
