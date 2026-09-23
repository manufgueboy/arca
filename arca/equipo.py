"""Conoce la Mac y prepara el modelo local sin que el usuario toque la terminal.

- Datos reales del equipo (para que el modelo no los invente).
- Catálogo de modelos por RAM y recomendación automática.
- Instalar Ollama (sin Homebrew) y descargar modelos con barra de progreso.
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable

OLLAMA = "http://localhost:11434"
OLLAMA_ZIP = "https://ollama.com/download/Ollama-darwin.zip"

# Modelos recomendados (Qwen 3.5: herramientas, visión y 256K de contexto).
# ram_min = RAM total mínima para que corra cómodo junto con tus apps.
CATALOGO = [
    {"id": "qwen3.5:4b", "nombre": "Arca Ligero", "gb": 3.4, "ram_min": 8,
     "desc": "Rápido. Para Macs de 8 GB. Bien para tareas sencillas."},
    {"id": "qwen3.5:9b", "nombre": "Arca Equilibrado", "gb": 6.6, "ram_min": 16,
     "desc": "El mejor balance. Para Macs de 16 GB o más."},
    {"id": "qwen3.5:27b", "nombre": "Arca Pro", "gb": 17, "ram_min": 32,
     "desc": "Muy capaz. Para Macs de 32 GB o más."},
    {"id": "qwen3.5:35b", "nombre": "Arca Max", "gb": 24, "ram_min": 48,
     "desc": "El más inteligente que corre local. 48 GB o más."},
]

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _sh(cmd: list[str], timeout: int = 5) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def ram_gb() -> int:
    if platform.system() == "Darwin":
        v = _sh(["sysctl", "-n", "hw.memsize"])
        if v.isdigit():
            return round(int(v) / 1024 ** 3)
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return 8


def disco_libre_gb() -> float:
    return round(shutil.disk_usage(Path.home()).free / 1024 ** 3, 1)


def chip() -> str:
    if platform.system() != "Darwin":
        return platform.machine()
    return _sh(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.machine()


def num_ctx_para_ram(ram: int) -> int:
    return 8192 if ram <= 8 else 16384 if ram <= 24 else 32768


def recomendar(ram: int | None = None, libre: float | None = None) -> dict:
    ram = ram or ram_gb()
    libre = disco_libre_gb() if libre is None else libre
    opciones = [m for m in CATALOGO if m["ram_min"] <= ram and m["gb"] + 3 <= libre] or [CATALOGO[0]]
    return opciones[-1]


_CACHE: dict = {}


def contexto() -> str:
    """Datos reales del equipo y del calendario para el prompt del sistema."""
    if "fijo" not in _CACHE:
        mac = platform.mac_ver()[0]
        so = f"macOS {mac}" if mac else f"{platform.system()} {platform.release()}"
        modelo_mac = _sh(["sysctl", "-n", "hw.model"]) if mac else ""
        _CACHE["fijo"] = f"{so} · {chip()} {modelo_mac} · {ram_gb()} GB de RAM"
    ahora = datetime.datetime.now().astimezone()
    hoy = ahora.date()
    def fecha(d):
        return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} ({d.isoformat()})"
    proximos = ", ".join(
        f"{DIAS[d.weekday()]} {d.isoformat()}" for d in (hoy + datetime.timedelta(days=i) for i in range(3, 8)))
    return (
        f"- Equipo: {_CACHE['fijo']} · {disco_libre_gb()} GB libres en disco\n"
        f"- Hoy: {fecha(hoy)} {hoy.year}, son las {ahora.strftime('%H:%M')} (zona {ahora.strftime('%Z %z')})\n"
        f"- Mañana: {fecha(hoy + datetime.timedelta(days=1))} · Pasado mañana: {fecha(hoy + datetime.timedelta(days=2))}\n"
        f"- Siguientes días: {proximos}\n"
        f"- Carpeta actual (\"aquí\", \"esta carpeta\"; las rutas relativas son desde aquí): {os.getcwd()}\n"
        f"- Carpeta personal del usuario (~): {Path.home()} · Descargas = ~/Downloads · Escritorio = ~/Desktop · Documentos = ~/Documents"
    )


# ───────────────────────────── Ollama ──────────────────────────────

def ollama_corriendo() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def ollama_instalado() -> bool:
    return bool(shutil.which("ollama")) or any(
        p.exists() for p in (Path("/Applications/Ollama.app"), Path.home() / "Applications/Ollama.app"))


def modelos_locales() -> list[dict]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return []
    return [{"id": m["name"], "gb": round(m.get("size", 0) / 1024 ** 3, 1),
             "params": (m.get("details") or {}).get("parameter_size", "")}
            for m in data.get("models", []) if "cloud" not in m["name"] and "embed" not in m["name"]
            and "bge" not in m["name"]]


def iniciar_ollama(espera: int = 60) -> bool:
    if ollama_corriendo():
        return True
    if platform.system() == "Darwin":
        subprocess.run(["open", "-g", "-a", "Ollama"], capture_output=True)
        for _ in range(15):
            if ollama_corriendo():
                return True
            time.sleep(1)
    binario = shutil.which("ollama") or next((str(p) for p in (
        Path("/Applications/Ollama.app/Contents/Resources/ollama"),
        Path.home() / "Applications/Ollama.app/Contents/Resources/ollama") if p.exists()), None)
    if binario and not ollama_corriendo():
        subprocess.Popen([binario, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    for _ in range(espera):
        if ollama_corriendo():
            return True
        time.sleep(1)
    return False


def instalar_ollama(progreso: Callable[[str, float], None] = lambda t, p: None) -> bool:
    """Descarga la app oficial de Ollama y la pone en Aplicaciones (sin Homebrew)."""
    if platform.system() != "Darwin":
        progreso("Instala Ollama desde https://ollama.com/download", 0)
        return False
    if ollama_instalado():
        progreso("Iniciando Ollama…", 0.9)
        return iniciar_ollama()
    destino = Path("/Applications") if os.access("/Applications", os.W_OK) else Path.home() / "Applications"
    destino.mkdir(exist_ok=True)
    zip_path = Path.home() / ".arca" / "Ollama-darwin.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(OLLAMA_ZIP, headers={"User-Agent": "Arca"})
    with urllib.request.urlopen(req, timeout=60) as r, open(zip_path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        hecho = 0
        while True:
            trozo = r.read(1 << 20)
            if not trozo:
                break
            f.write(trozo)
            hecho += len(trozo)
            progreso("Descargando Ollama…", hecho / total * 0.8 if total else 0.4)
    progreso("Instalando Ollama…", 0.85)
    subprocess.run(["ditto", "-x", "-k", str(zip_path), str(destino)], check=True)
    zip_path.unlink(missing_ok=True)
    progreso("Iniciando Ollama…", 0.9)
    return iniciar_ollama()


def descargar_modelo(modelo: str, progreso: Callable[[str, float], None] = lambda t, p: None) -> None:
    """Descarga un modelo por la API de Ollama con progreso (0..1). Lanza RuntimeError si falla."""
    req = urllib.request.Request(f"{OLLAMA}/api/pull", data=json.dumps({"model": modelo}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    partes: dict[str, list[int]] = {}   # el modelo viene en varias capas: sumamos todas para que la barra no regrese a 0
    with urllib.request.urlopen(req, timeout=3600) as r:
        for linea in r:
            if not linea.strip():
                continue
            ev = json.loads(linea)
            if ev.get("error"):
                raise RuntimeError(ev["error"])
            estado = ev.get("status", "")
            if ev.get("total"):
                partes[ev.get("digest") or estado] = [ev.get("completed", 0), ev["total"]]
                hecho = sum(c for c, _ in partes.values())
                total = sum(t for _, t in partes.values())
                progreso(f"Descargando {modelo}… {hecho / 1024 ** 3:.1f} de {total / 1024 ** 3:.1f} GB", hecho / total)
            elif estado == "success":
                progreso("Listo", 1.0)
            else:
                progreso(estado.capitalize() + "…", -1)
