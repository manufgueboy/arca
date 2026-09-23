"""Línea de comandos de Arca.

  arca web                     abre Arca en el navegador (sin terminal)
  arca                         chat interactivo en la terminal
  arca "haz tal cosa"          una sola tarea y sale
  arca modelos [--gratis]      lista modelos del proveedor actual
  arca usar <proveedor> [modelo]
  arca login <proveedor>       guarda una API key
  arca proveedores             lista proveedores disponibles
  arca skills                  lista skills
  arca skill-nueva <nombre>    crea una skill en ~/.arca/skills
  arca descargar [modelo]      descarga el modelo local recomendado para tu Mac
  arca doctor                  revisa que todo esté bien
  arca actualizar              baja la última versión
Opciones: -p/--proveedor, -m/--modelo, -y/--auto (no pedir confirmación)
"""
from __future__ import annotations

import getpass
import json
import sys
import urllib.request

from . import __version__, config, equipo, providers, skills, tools
from .agent import Agente

C = {"gris": "\033[90m", "cian": "\033[36m", "verde": "\033[32m", "amarillo": "\033[33m",
     "rojo": "\033[31m", "neg": "\033[1m", "x": "\033[0m"}
if not sys.stdout.isatty():
    C = {k: "" for k in C}


def color(txt: str, c: str) -> str:
    return f"{C[c]}{txt}{C['x']}"


def _resumen_args(args: dict) -> str:
    partes = []
    for k, v in args.items():
        v = str(v).replace("\n", "⏎")
        partes.append(f"{k}={v[:70] + '…' if len(v) > 70 else v}")
    return ", ".join(partes)


class Sesion:
    def __init__(self, cfg: dict, proveedor: str | None, modelo: str | None, auto: bool):
        self.cfg = cfg
        self.auto = auto or cfg.get("auto_aprobar", False)
        self.prov = providers.crear(cfg, proveedor, modelo)
        self.agente = Agente(self.prov, cfg.get("max_pasos", 30), self.confirmar, self.mostrar,
                             modo=cfg.get("modo", "auto"))

    def mostrar(self, nombre: str, args: dict) -> None:
        print(color(f"  ⚙ {nombre}", "cian") + color(f"({_resumen_args(args)})", "gris"))

    def confirmar(self, nombre: str, args: dict) -> bool:
        if self.auto:
            return True
        if nombre in ("terminal", "applescript", "chrome_js", "escribir_archivo", "organizar_carpeta"):
            detalle = args.get("comando") or args.get("script") or args.get("codigo") or args.get("ruta")
            if nombre == "organizar_carpeta":
                detalle = tools.organizar_carpeta(args.get("ruta", "."), "no")
            print(color("    ┌\n", "gris") + "\n".join(color("    │ ", "gris") + l for l in str(detalle).splitlines()[:25]))
        try:
            r = input(color("    ¿Permitir? [s]í / [n]o / [t]odo esta sesión: ", "amarillo")).strip().lower()
        except EOFError:
            return False
        if r.startswith("t"):
            self.auto = True
            return True
        return r in ("", "s", "si", "sí", "y", "yes")

    def etiqueta(self) -> str:
        return f"{self.prov.nombre}/{self.prov.modelo}"

    def tarea(self, texto: str) -> None:
        try:
            print(color("  … pensando", "gris"))
            print("\n" + self.agente.preguntar(texto) + "\n")
        except KeyboardInterrupt:
            self.agente.reparar()
            print(color("\n  ✋ Interrumpido.\n", "amarillo"))
        except providers.ProveedorError as e:
            self.agente.reparar()
            print(color(f"\n  Error del modelo: {e}\n", "rojo"))

    def repl(self) -> None:
        try:
            import readline  # noqa: F401  (historial con flechas)
        except ImportError:
            pass
        modo = " · modo compacto" if self.agente.compacto else ""
        print(color(f"\n  ⛵ Arca {__version__}", "neg") + color(f"  ·  {self.etiqueta()}{modo}  ·  "
              f"{len(skills.cargar())} skills  ·  /ayuda", "gris"))
        print(color("  Pídeme lo que sea: archivos, apps de tu Mac, Chrome, terminal, web.\n", "gris"))
        while True:
            try:
                texto = input(color("› ", "verde")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not texto:
                continue
            if texto.startswith("/"):
                if self.comando(texto) == "salir":
                    return
                continue
            self.tarea(texto)

    def comando(self, linea: str) -> str | None:
        partes = linea[1:].split()
        cmd, args = partes[0].lower(), partes[1:]
        if cmd in ("salir", "exit", "q"):
            return "salir"
        if cmd in ("nuevo", "limpiar", "clear"):
            self.agente.nuevo()
            print(color("  Conversación nueva.", "gris"))
        elif cmd == "modelo":
            if args:
                self.prov.modelo = args[0]
                self.agente.configurar_modelo()
            print(color(f"  Modelo: {self.etiqueta()}", "gris"))
        elif cmd == "proveedor" and args:
            try:
                self.prov = providers.crear(self.cfg, args[0], args[1] if len(args) > 1 else None)
                self.agente.prov = self.prov
                self.agente.modo_texto = False
                self.agente.configurar_modelo()
                print(color(f"  Ahora: {self.etiqueta()}", "gris"))
            except providers.ProveedorError as e:
                print(color(f"  {e}", "rojo"))
        elif cmd == "modelos":
            imprimir_modelos(self.prov, "gratis" in args)
        elif cmd == "skills":
            imprimir_skills()
        elif cmd == "auto":
            self.auto = not self.auto
            print(color(f"  Auto-aprobar: {'sí' if self.auto else 'no'}", "gris"))
        else:
            print(color("  /modelo <id>  /proveedor <nombre> [modelo]  /modelos [gratis]  /skills\n"
                        "  /auto (no pedir permiso)  /nuevo (borrar conversación)  /salir\n"
                        "  Ctrl-C interrumpe una tarea a medias.", "gris"))
        return None


def imprimir_modelos(prov, solo_gratis: bool = False) -> None:
    try:
        ms = prov.listar_modelos()
    except providers.ProveedorError as e:
        print(color(f"  {e}", "rojo"))
        return
    if solo_gratis:
        ms = [m for m in ms if m["gratis"]]
    for m in ms:
        marcas = (color(" gratis", "verde") if m["gratis"] else "") + ("" if m["tools"] else color(" (sin tools)", "gris"))
        print(f"  {m['id']}{marcas}")
    print(color(f"  {len(ms)} modelos · actual: {prov.modelo}", "gris"))


def imprimir_skills() -> None:
    for s in skills.cargar().values():
        print(f"  {color(s.nombre, 'cian')}  {s.descripcion}")
        print(color(f"    {s.path}", "gris"))


def barra(texto: str, pct: float) -> None:
    if pct < 0:
        print(f"\r  {texto:<40}", end="", flush=True)
        return
    n = int(pct * 30)
    print(f"\r  {texto[:32]:<32} [{'█' * n}{'·' * (30 - n)}] {pct * 100:5.1f}%", end="", flush=True)


def descargar(cfg: dict, modelo: str | None) -> None:
    ram, libre = equipo.ram_gb(), equipo.disco_libre_gb()
    rec = equipo.recomendar(ram, libre)
    modelo = modelo or rec["id"]
    print(f"  Tu Mac: {ram} GB de RAM, {libre} GB libres → {color(modelo, 'cian')}")
    if not equipo.ollama_corriendo():
        print("  Preparando Ollama…")
        if not equipo.instalar_ollama(barra):
            print(color("\n  No pude iniciar Ollama. Ábrelo desde Aplicaciones y reintenta.", "rojo"))
            return
        print()
    try:
        equipo.descargar_modelo(modelo, barra)
    except RuntimeError as e:
        print(color(f"\n  Error: {e}", "rojo"))
        return
    print()
    cfg["proveedor"], cfg["modelo"] = "ollama", modelo
    config.guardar(cfg)
    print(color(f"  ✓ Listo. Arca usará {modelo}. Escribe: arca", "verde"))


def sin_modelo(cfg: dict) -> bool:
    """Primer uso: no hay modelo local. Ofrece descargar el recomendado."""
    if cfg["proveedor"] != "ollama":
        return False
    if equipo.ollama_instalado() and not equipo.ollama_corriendo():
        print(color("  Encendiendo Ollama…", "gris"))
        equipo.iniciar_ollama()
    if cfg.get("modelo") or equipo.modelos_locales():
        return False
    rec = equipo.recomendar()
    print(color("\n  👋 Bienvenido a Arca. Aún no tienes un modelo de IA.", "neg"))
    print(f"  Recomendado para tu Mac: {color(rec['nombre'], 'cian')} ({rec['id']}, {rec['gb']} GB) — {rec['desc']}")
    print(color("  (Si prefieres botones en vez de terminal, escribe: arca web)", "gris"))
    try:
        r = input("  ¿Lo descargo ahora? [S/n] ").strip().lower()
    except EOFError:
        r = "n"
    if r in ("", "s", "si", "sí", "y"):
        descargar(cfg, rec["id"])
        return False
    return True


def doctor(cfg: dict) -> None:
    ok = lambda b: color("✓", "verde") if b else color("✗", "rojo")
    print(f"  {ok(sys.version_info >= (3, 9))} Python {sys.version.split()[0]}")
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        print(f"  {ok(True)} Ollama corriendo")
    except Exception:
        print(f"  {ok(False)} Ollama no responde (instala: brew install ollama && ollama serve)")
    try:
        p = providers.crear(cfg)
        print(f"  {ok(True)} Proveedor {p.nombre} · modelo {p.modelo}")
    except providers.ProveedorError as e:
        print(f"  {ok(False)} {e}")
    if tools.ES_MAC:
        r = tools._osascript('tell application "System Events" to (name of processes) contains "Google Chrome"')
        if r == "true":
            js = tools._chrome_js("1+1")
            print(f"  {ok(js == '2')} Chrome + JavaScript de eventos de Apple" + ("" if js == "2" else f"\n     {js}"))
        else:
            print(f"  {color('·', 'gris')} Chrome no está abierto (ábrelo para revisar el permiso de JavaScript)")
    print(f"  {ok(True)} {len(skills.cargar())} skills · config en {config.CONFIG_PATH}")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = config.cargar()
    prov_arg = modelo_arg = None
    auto = False
    resto = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-p", "--proveedor") and i + 1 < len(argv):
            prov_arg, i = argv[i + 1], i + 2
        elif a in ("-m", "--modelo") and i + 1 < len(argv):
            modelo_arg, i = argv[i + 1], i + 2
        elif a in ("-y", "--auto"):
            auto, i = True, i + 1
        elif a in ("-h", "--help", "ayuda"):
            print(__doc__)
            return
        elif a in ("-v", "--version"):
            print(__version__)
            return
        else:
            resto.append(a)
            i += 1

    cmd = resto[0] if resto else ""
    try:
        if cmd == "proveedores":
            for n, d in config.proveedores(cfg).items():
                if not d.get("env"):
                    estado = color("local ", "verde")
                elif config.api_key(cfg, n, d):
                    estado = color("key ✓ ", "verde")
                else:
                    estado = color("sin key", "gris")
                print(f"  {estado} {color(n, 'cian'):<22} {d.get('descripcion', d.get('base_url', ''))}")
            print(color(f"\n  Actual: {cfg['proveedor']}  ·  cambiar: arca usar <proveedor> [modelo]", "gris"))
        elif cmd == "login":
            nombre = resto[1] if len(resto) > 1 else input("Proveedor: ").strip()
            key = getpass.getpass(f"API key de {nombre} (no se muestra): ").strip()
            cfg.setdefault("api_keys", {})[nombre] = key
            config.guardar(cfg)
            print(color(f"  Guardada en {config.CONFIG_PATH} (solo tu usuario puede leerla).", "verde"))
        elif cmd == "usar":
            if len(resto) < 2:
                print("Uso: arca usar <proveedor> [modelo]")
                return
            cfg["proveedor"] = resto[1]
            cfg["modelo"] = resto[2] if len(resto) > 2 else ""
            p = providers.crear(cfg)
            cfg["modelo"] = p.modelo
            config.guardar(cfg)
            print(color(f"  Listo: {p.nombre}/{p.modelo}", "verde"))
        elif cmd == "modelos":
            prov = providers.crear(cfg, prov_arg, modelo_arg or "-")
            if not modelo_arg:
                nombre = prov_arg or cfg["proveedor"]
                prov.modelo = (cfg.get("modelo") if nombre == cfg["proveedor"] else "") or "(automático)"
            imprimir_modelos(prov, "--gratis" in resto or "gratis" in resto)
        elif cmd == "skills":
            imprimir_skills()
        elif cmd == "skill-nueva":
            print(color(f"  Creada: {skills.nueva(resto[1])}", "verde"))
        elif cmd == "doctor":
            doctor(cfg)
        elif cmd == "web":
            from .web import servir
            servir(abrir="--no-abrir" not in resto)
        elif cmd == "descargar":
            descargar(cfg, resto[1] if len(resto) > 1 else None)
        elif cmd == "actualizar":
            import subprocess
            subprocess.run("curl -fsSL https://raw.githubusercontent.com/manufgueboy/arca/main/install.sh | bash",
                           shell=True)
        elif cmd == "config":
            print(json.dumps({**cfg, "api_keys": {k: "••••" for k in cfg.get("api_keys", {})}}, indent=2, ensure_ascii=False))
            print(color(f"  {config.CONFIG_PATH}", "gris"))
        else:
            if not prov_arg and not modelo_arg and sin_modelo(cfg):
                return
            cfg = config.cargar()
            s = Sesion(cfg, prov_arg, modelo_arg, auto)
            if resto:
                s.tarea(" ".join(resto))
            else:
                s.repl()
    except providers.ProveedorError as e:
        print(color(f"  {e}", "rojo"))
        sys.exit(1)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
