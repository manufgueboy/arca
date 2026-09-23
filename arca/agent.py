"""El loop agéntico: el modelo piensa → pide herramientas → Arca las ejecuta → repite.

Funciona con cualquier modelo:
- Modo nativo: modelos con function calling (la mayoría de los modernos).
- Modo texto: si el modelo no soporta tools, se describen en el prompt y el
  modelo responde con bloques ```tool {json}```. Así hasta un modelo chico
  y gratis puede ser agente.
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import re
from typing import Callable

from . import skills, tools
from .providers import ToolsNoSoportadas

SISTEMA = """Eres Arca, un agente de IA que trabaja en la computadora del usuario ({so}).
Hoy es {fecha}. Carpeta actual: {cwd}. Usuario: {usuario}.

Puedes actuar de verdad con tus herramientas: archivos, terminal, AppleScript para controlar
la Mac y sus apps, Google Chrome (abrir, leer, dar clic, escribir), búsqueda web y skills.

Cómo trabajar:
- Si la tarea coincide con una skill, cárgala primero con usar_skill y sigue sus pasos.
- Usa herramientas para verificar en vez de adivinar. No inventes datos.
- En Chrome: chrome_abrir → chrome_leer (te da los elementos numerados) → chrome_clic / chrome_escribir.
- Ve paso a paso. Si una herramienta falla, lee el error y corrige.
- Cuando termines, responde breve y claro, en el idioma del usuario, sin llamar más herramientas.

Skills instaladas:
{skills}
"""

PROTOCOLO_TEXTO = """

Tu modelo no tiene herramientas nativas. Para usar una, responde SOLO con:
```tool
{{"herramienta": "nombre", "argumentos": {{"param": "valor"}}}}
```
Yo te regreso el resultado y sigues. Cuando tengas la respuesta final, escríbela normal, sin bloque tool.

Herramientas disponibles:
{lista}
"""

_BLOQUE = re.compile(r"```(?:tool|json)?\s*\n?(\{.*?\})\s*\n?```", re.S)


def _sistema(modo_texto: bool) -> str:
    s = SISTEMA.format(so=f"{platform.system()} {platform.mac_ver()[0] or platform.release()}",
                       fecha=datetime.date.today().isoformat(), cwd=os.getcwd(),
                       usuario=os.environ.get("USER", ""), skills=skills.resumen())
    if modo_texto:
        lista = "\n".join(
            f"- {t.nombre}({', '.join(t.esquema['function']['parameters']['properties'])}): "
            f"{t.esquema['function']['description']}" for t in tools.REGISTRO.values())
        s += PROTOCOLO_TEXTO.format(lista=lista)
    return s


class Agente:
    def __init__(self, proveedor, max_pasos: int = 30,
                 confirmar: Callable[[str, dict], bool] | None = None,
                 mostrar: Callable[[str, dict], None] | None = None):
        self.prov = proveedor
        self.max_pasos = max_pasos
        self.confirmar = confirmar or (lambda n, a: True)
        self.mostrar = mostrar or (lambda n, a: None)
        self.modo_texto = False
        self.historial: list[dict] = []

    def nuevo(self) -> None:
        self.historial = []

    def reparar(self) -> None:
        """Tras un Ctrl-C: cierra llamadas a herramientas que quedaron sin resultado."""
        respondidas = {m.get("tool_call_id") for m in self.historial if m["role"] == "tool"}
        for i, m in enumerate(list(self.historial)):
            for c in m.get("tool_calls") or []:
                cid = c.get("id") or c["function"]["name"]
                if cid not in respondidas:
                    self.historial.append({"role": "tool", "tool_call_id": cid, "name": c["function"]["name"],
                                           "content": "[interrumpido por el usuario]"})
        if self.historial and self.historial[-1]["role"] != "assistant":
            self.historial.append({"role": "assistant", "content": "(interrumpido)"})

    def _mensajes(self) -> list[dict]:
        return [{"role": "system", "content": _sistema(self.modo_texto)}] + self.historial

    def _correr_tool(self, nombre: str, args: dict) -> str:
        self.mostrar(nombre, args)
        t = tools.REGISTRO.get(nombre)
        if t and t.riesgo and not self.confirmar(nombre, args):
            return "[cancelado] El usuario no autorizó esta acción. Pregúntale cómo seguir o usa otra vía."
        return tools.ejecutar(nombre, args)

    def preguntar(self, texto: str) -> str:
        self.historial.append({"role": "user", "content": texto})
        for _ in range(self.max_pasos):
            if self.modo_texto:
                resp = self.prov.chat(self._mensajes())
            else:
                try:
                    resp = self.prov.chat(self._mensajes(), tools.esquemas())
                except ToolsNoSoportadas:
                    self.modo_texto = True
                    continue

            calls = resp.get("tool_calls") or []
            contenido = resp.get("content") or ""

            if calls:
                self.historial.append({"role": "assistant", "content": contenido, "tool_calls": calls})
                for c in calls:
                    fn = c["function"]
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args or "{}")
                        except json.JSONDecodeError:
                            args = {}
                    salida = self._correr_tool(fn["name"], args)
                    self.historial.append({"role": "tool", "tool_call_id": c.get("id") or fn["name"],
                                           "name": fn["name"], "content": salida})
                continue

            # ¿El modelo pidió una herramienta por texto?
            m = _BLOQUE.search(contenido)
            if m:
                try:
                    spec = json.loads(m.group(1))
                    nombre = spec.get("herramienta") or spec.get("name") or spec.get("tool")
                    args = spec.get("argumentos") or spec.get("arguments") or {}
                except json.JSONDecodeError:
                    nombre = None
                if nombre in tools.REGISTRO:
                    self.historial.append({"role": "assistant", "content": contenido})
                    salida = self._correr_tool(nombre, args)
                    self.historial.append({"role": "user", "content": f"[resultado de {nombre}]\n{salida}"})
                    continue

            self.historial.append({"role": "assistant", "content": contenido})
            return contenido or "(sin respuesta)"

        return "[Arca] Llegué al límite de pasos. Dime si sigo."
