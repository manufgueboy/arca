"""Skills: carpetas con un SKILL.md (mismo formato que las skills de Claude).

    ---
    name: mi-skill
    description: Cuándo usarla.
    ---
    Instrucciones paso a paso…

Se buscan en <repo>/skills y en ~/.arca/skills (las del usuario ganan).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import ARCA_HOME

CARPETAS = [Path(__file__).resolve().parent.parent / "skills", ARCA_HOME / "skills"]


@dataclass
class Skill:
    nombre: str
    descripcion: str
    cuerpo: str
    path: Path


def _parse(texto: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", texto, re.S)
    if not m:
        return {}, texto.strip()
    meta = {}
    for linea in m.group(1).splitlines():
        if ":" in linea and not linea.startswith(" "):
            k, _, v = linea.partition(":")
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, m.group(2).strip()


def cargar() -> dict[str, Skill]:
    todas: dict[str, Skill] = {}
    for carpeta in CARPETAS:
        if not carpeta.is_dir():
            continue
        for sub in sorted(carpeta.iterdir()):
            f = sub / "SKILL.md"
            if f.is_file():
                meta, cuerpo = _parse(f.read_text(encoding="utf-8"))
                s = Skill(meta.get("name", sub.name), meta.get("description", ""), cuerpo, sub)
                todas[s.nombre] = s
    return todas


def resumen() -> str:
    s = cargar()
    return "\n".join(f"- {x.nombre}: {x.descripcion}" for x in s.values()) or "(ninguna)"


def nueva(nombre: str) -> Path:
    carpeta = ARCA_HOME / "skills" / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    f = carpeta / "SKILL.md"
    if not f.exists():
        f.write_text(f"---\nname: {nombre}\ndescription: Describe aquí cuándo debe usarse esta skill.\n---\n\n"
                     "# Instrucciones\n\n1. Primer paso…\n2. Segundo paso…\n", encoding="utf-8")
    return f
