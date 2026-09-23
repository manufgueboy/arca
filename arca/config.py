"""Configuración de Arca: ~/.arca/config.json (solo librería estándar)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ARCA_HOME = Path(os.environ.get("ARCA_HOME", Path.home() / ".arca"))
CONFIG_PATH = ARCA_HOME / "config.json"

# Proveedores listos para usar. Todos (menos Anthropic) hablan el API estilo
# OpenAI, así que con una sola clase cubrimos locales, gratis y de pago.
PRESETS: dict[str, dict] = {
    # --- Locales (gratis, privados, sin internet) ---
    "ollama": {
        "tipo": "ollama",
        "base_url": "http://localhost:11434",
        "api_key": "ollama",
        "descripcion": "Modelos locales con Ollama (gratis, privado, offline)",
    },
    "lmstudio": {
        "tipo": "openai",
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "descripcion": "Modelos locales con LM Studio (gratis, privado, offline)",
    },
    # --- En la nube con plan gratis ---
    "openrouter": {
        "tipo": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
        "descripcion": "Cientos de modelos, varios gratis (terminan en :free)",
    },
    "groq": {
        "tipo": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "env": "GROQ_API_KEY",
        "descripcion": "Modelos abiertos muy rápidos, con plan gratis",
    },
    "gemini": {
        "tipo": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env": "GEMINI_API_KEY",
        "descripcion": "Google Gemini, con plan gratis (aistudio.google.com)",
    },
    # --- De pago por API ---
    "openai": {
        "tipo": "openai",
        "base_url": "https://api.openai.com/v1",
        "env": "OPENAI_API_KEY",
        "descripcion": "OpenAI (de pago por uso)",
    },
    "anthropic": {
        "tipo": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "env": "ANTHROPIC_API_KEY",
        "descripcion": "Claude por API (de pago por uso)",
    },
}

DEFAULTS = {
    "proveedor": "ollama",
    "modelo": "",            # vacío = Arca elige uno disponible
    "auto_aprobar": False,   # True = no pide confirmación antes de acciones
    "max_pasos": 30,
    "modo": "auto",          # auto | compacto | completo  (compacto = optimizado para modelos chicos)
    "proveedores": {},       # overrides o proveedores propios, mismo formato que PRESETS
    "api_keys": {},          # llaves guardadas con `arca login <proveedor>`
}


def cargar() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def guardar(cfg: dict) -> None:
    ARCA_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)  # contiene API keys
    except OSError:
        pass


def proveedores(cfg: dict) -> dict[str, dict]:
    todos = {k: dict(v) for k, v in PRESETS.items()}
    for nombre, datos in cfg.get("proveedores", {}).items():
        todos.setdefault(nombre, {"tipo": "openai"}).update(datos)
    return todos


def api_key(cfg: dict, nombre: str, datos: dict) -> str:
    if datos.get("api_key"):
        return datos["api_key"]
    if nombre in cfg.get("api_keys", {}):
        return cfg["api_keys"][nombre]
    env = datos.get("env")
    if env and os.environ.get(env):
        return os.environ[env]
    return ""
