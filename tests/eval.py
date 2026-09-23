"""Evaluación con un modelo real: ¿qué tan bien resuelve tareas del día a día?

Uso:  python3 tests/eval.py --modelo qwen3.5:4b [--repo RUTA] [--reps 1]

Las acciones con efectos (recordatorios, correos, notificaciones, abrir apps, AppleScript, JS en Chrome)
se REGISTRAN pero no se ejecutan. Todo lo de archivos pasa en una carpeta temporal.
"""
import argparse
import datetime
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--modelo", default="qwen3.5:4b")
ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
ap.add_argument("--reps", type=int, default=1)
ap.add_argument("--solo", default="")
ap.add_argument("--json", default="")
a = ap.parse_args()

sys.path.insert(0, a.repo)
os.environ["ARCA_HOME"] = tempfile.mkdtemp()
# CAJA DE ARENA: la "carpeta personal" es temporal y ninguna herramienta puede salir de ella.
CAJA = Path(tempfile.mkdtemp(prefix="arca-eval-")).resolve()
os.environ["HOME"] = str(CAJA)
for sub in ("Downloads", "Desktop", "Documents"):
    (CAJA / sub).mkdir()
config = importlib.import_module("arca.config")
providers = importlib.import_module("arca.providers")
tools = importlib.import_module("arca.tools")
Agente = importlib.import_module("arca.agent").Agente

EFECTOS = {"terminal", "crear_recordatorio", "crear_evento", "borrador_correo", "notificar", "abrir", "applescript",
           "chrome_js", "chrome_abrir", "chrome_clic", "chrome_escribir"}
registro: list = []


_ruta_original = tools._ruta


def _ruta_encerrada(p):
    r = _ruta_original(p)
    if r != CAJA and CAJA not in r.parents:
        raise PermissionError(f"[eval] ruta fuera de la caja de arena: {r}")
    return r


tools._ruta = _ruta_encerrada


def interceptar():
    for nombre in list(tools.REGISTRO):
        if nombre in EFECTOS:
            def rec(_n=nombre, **kw):
                registro.append((_n, kw))
                if _n == "terminal":   # solo comandos de lectura, dentro de la caja
                    cmd = kw.get("comando", "")
                    if re.search(r"\b(rm|mv|cp|chmod|sudo|curl|>)\b", cmd) or "/Users/" in cmd.replace(str(CAJA), ""):
                        return "[eval] comando bloqueado"
                    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30,
                                       env={**os.environ, "HOME": str(CAJA)})
                    return (r.stdout + r.stderr).strip()[:4000] or "(sin salida)"
                if _n == "applescript" and "count of" in kw.get("script", ""):
                    return "3"
                return "[ok] hecho"
            tools.REGISTRO[nombre].fn = rec


hoy = datetime.date.today()
manana = hoy + datetime.timedelta(days=1)
pasado = hoy + datetime.timedelta(days=2)
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
version_mac = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip()
pestanas_reales = None
try:
    out = subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to count every tab of every window'],
                         capture_output=True, text=True, timeout=10).stdout
    pestanas_reales = sum(int(x) for x in re.findall(r"\d+", out))
except Exception:
    pass


def llamadas(nombre):
    return [kw for n, kw in registro if n == nombre]


def usa(*nombres):
    return any(n in nombres for n, _ in registro)


def prep(d: Path):
    (d / "nota.txt").write_text("la clave secreta es mango-77\n")
    des = d / "desorden"
    des.mkdir()
    for n in ("foto.jpg", "selfie.png", "contrato.pdf", "tabla.xlsx", "app.dmg"):
        (des / n).write_text("x")
    con = d / "conteo"
    con.mkdir()
    for i in range(7):
        (con / f"archivo{i}.txt").write_text("x")


def ok_recordatorio(r, d):
    for kw in llamadas("crear_recordatorio"):
        f = kw.get("fecha", "")
        if manana.isoformat() in f and "17" in f and "mam" in kw.get("texto", "").lower():
            return True
    for kw in llamadas("applescript"):
        s = kw.get("script", "")
        if "Reminders" in s and str(manana.day) in s and "17" in s:
            return True
    return False


def ok_correo(r, d):
    for kw in llamadas("borrador_correo"):
        if "juan@ejemplo.com" in kw.get("para", "") and "reporte" in (kw.get("cuerpo", "") + kw.get("asunto", "")).lower():
            return True
    for kw in llamadas("applescript"):
        s = kw.get("script", "")
        if "Mail" in s and "juan@ejemplo.com" in s and "send" not in s.split("juan@ejemplo.com")[-1]:
            return True
    return False


def ok_organizar(r, d):
    des = d / "desorden"
    sueltos = [f.name for f in des.iterdir() if f.is_file()]
    return not sueltos and any(p.is_dir() and (p / "foto.jpg").exists() for p in des.iterdir())


TAREAS = [
    ("mac_version", "¿qué versión de macOS tengo?", lambda r, d: version_mac in r),
    ("leer_archivo", "¿qué dice el archivo nota.txt de esta carpeta?", lambda r, d: "mango-77" in r),
    ("crear_archivo", "crea un archivo compras.txt en esta carpeta con la lista: leche, huevos y pan",
     lambda r, d: (d / "compras.txt").exists() and "pan" in (d / "compras.txt").read_text().lower()),
    ("contar", "¿cuántos archivos hay en la carpeta conteo?", lambda r, d: re.search(r"\b7\b|siete", r.lower()) is not None),
    ("organizar", "organiza la carpeta desorden que está aquí, por tipo de archivo. Ya tienes mi permiso", ok_organizar),
    ("recordatorio", "recuérdame mañana a las 5 de la tarde llamar a mamá", ok_recordatorio),
    ("fecha", "¿qué día de la semana será pasado mañana?", lambda r, d: DIAS[pasado.weekday()] in r.lower()),
    ("correo", "escribe un correo a juan@ejemplo.com pidiéndole el reporte de ventas", ok_correo),
    ("dato", "¿quién escribió Cien años de soledad y en qué año se publicó?",
     lambda r, d: "garcía márquez" in r.lower().replace("garcia", "garcía") and "1967" in r),
    ("actual", "¿cuál es la versión más reciente de Ollama? búscalo", lambda r, d: "0.3" in r and usa_web()),
    ("chrome", "¿cuántas pestañas tengo abiertas en Chrome?",
     lambda r, d: pestanas_reales is not None and re.search(rf"\b{pestanas_reales}\b", r) is not None),
    ("clima", "¿va a llover hoy en Ciudad de México?",
     lambda r, d: usa_web() and ("%" in r or "lluvia" in r.lower() or "llover" in r.lower())),
]


def usa_web():
    return any(n in ("buscar_web", "leer_web", "wikipedia", "clima") for n, _ in llamadas_reales)


llamadas_reales: list = []

resultados = []
cfg = config.cargar()
for rep in range(a.reps):
    for clave, pedido, check in TAREAS:
        if a.solo and clave not in a.solo.split(","):
            continue
        d = Path(tempfile.mkdtemp(dir=CAJA))
        prep(d)
        os.chdir(d)
        registro.clear()
        llamadas_reales.clear()
        interceptar()
        prov = providers.crear(cfg, "ollama", a.modelo)
        ag = Agente(prov, 12)
        orig = ag._correr_tool

        def espia(n, args, _o=orig):
            llamadas_reales.append((n, args))
            return _o(n, args)
        ag._correr_tool = espia
        t0 = time.time()
        try:
            r = ag.preguntar(pedido)
        except Exception as e:
            r = f"[EXCEPCIÓN] {e}"
        dt = time.time() - t0
        try:
            bien = bool(check(r, d))
        except Exception:
            bien = False
        herramientas = [n for n, _ in llamadas_reales]
        resultados.append({"tarea": clave, "ok": bien, "seg": round(dt, 1), "tools": herramientas,
                           "respuesta": r[:300]})
        print(f"{'✅' if bien else '❌'} {clave:<14} {dt:5.1f}s  {herramientas}  →  {r[:140]!r}", flush=True)
        shutil.rmtree(d, ignore_errors=True)

n = len(resultados)
ok = sum(r["ok"] for r in resultados)
print(f"\nRESULTADO {a.modelo}: {ok}/{n} ({100 * ok // max(n, 1)}%) · "
      f"tiempo medio {sum(r['seg'] for r in resultados) / max(n, 1):.1f}s")
if a.json:
    Path(a.json).write_text(json.dumps(resultados, ensure_ascii=False, indent=2))
