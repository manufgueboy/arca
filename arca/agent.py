"""El loop agéntico: el modelo pide herramientas → Arca las ejecuta → repite.

Diseñado para que hasta un modelo chico (4B) sea útil:

- Contexto real inyectado (equipo, fecha, calendario): no tiene que adivinar.
- Modo compacto (automático en modelos ≤ 10B): prompt corto, solo las herramientas
  relevantes al pedido, resultados recortados, temperatura baja, sin "pensar".
- La skill que aplica se carga sola (el modelo chico casi nunca la pide).
- Si contesta sin actuar cuando debía, se le exige una vez que use herramientas.
- Si repite la misma llamada, se le frena.
- Modo texto: si el modelo no soporta herramientas nativas, usa bloques ```tool```.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from . import equipo, skills, tools
from .providers import ToolsNoSoportadas

SISTEMA_COMPLETO = """Eres Arca, un agente de IA que trabaja en la computadora del usuario.

Contexto real (úsalo; no lo adivines):
{contexto}

Puedes actuar de verdad con tus herramientas: archivos, terminal, apps de la Mac (Recordatorios,
Calendario, Mail, AppleScript), Google Chrome (abrir, leer, dar clic, escribir), web, Wikipedia y skills.

Cómo trabajar:
- Prefiere las herramientas específicas (crear_recordatorio, crear_evento, borrador_correo,
  organizar_carpeta, wikipedia…) antes que terminal o applescript.
- Tu respuesta final debe basarse SOLO en el contexto de arriba y en lo que devolvieron las
  herramientas. Nunca inventes datos. Si no sabes algo actual, búscalo.
- En Chrome: chrome_abrir → chrome_leer (elementos numerados) → chrome_clic / chrome_escribir.
- Si una herramienta falla, lee el error, corrige y reintenta.
- Las acciones que cambian algo le piden permiso al usuario solas: no le pidas permiso tú.
- Al terminar, responde breve y claro, en el idioma del usuario.

Skills instaladas (cárgalas con usar_skill cuando apliquen):
{skills}
"""

SISTEMA_COMPACTO = """Eres Arca, un asistente que ACTÚA en la Mac del usuario usando herramientas.

Datos reales (úsalos tal cual, no inventes otros):
{contexto}

Reglas:
1. Si el pedido requiere hacer algo o un dato que no está arriba, LLAMA a una herramienta. No respondas de memoria.
2. Usa la herramienta más específica. Fechas en formato AAAA-MM-DD HH:MM.
3. Responde SOLO con lo que devolvieron las herramientas. Si algo falló, dilo.
4. No pidas permiso: Arca se lo pide al usuario solo.
5. Respuesta final: corta, en español, sin inventar.
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

# Pedidos que claramente requieren actuar (si el modelo contesta sin herramientas, se le insiste).
_VERBOS_ACCION = re.compile(
    r"\b(crea|crear|haz|hacer|abre|abrir|busca|buscar|investiga|organiza|ordena|mueve|borra|elimina|escribe|"
    r"guarda|manda|envía|envia|pon|agrega|añade|agenda|recuérdame|recuerdame|lee|leer|resume|resumir|"
    r"descarga|instala|revisa|checa|dime|cuántos|cuantos|cuánto|cuanto|lista|muestra|ejecuta|corre|"
    r"clima|convierte|calcula|traduce)\b", re.I)

_BLOQUE = re.compile(r"```(?:tool|json)?\s*\n?(\{.*?)```", re.S)


def _leer_bloque(texto: str):
    """(nombre, args) si el texto trae una llamada tipo ```tool {...}```; None si no."""
    m = _BLOQUE.search(texto)
    if not m:
        return None
    try:
        spec, _ = json.JSONDecoder().raw_decode(m.group(1).strip())
    except json.JSONDecodeError as e:
        return ("", {"_error": f"JSON inválido: {e}"})
    if not isinstance(spec, dict):
        return ("", {"_error": "el bloque debe ser un objeto JSON"})
    nombre = spec.get("herramienta") or spec.get("name") or spec.get("tool") or ""
    args = spec.get("argumentos") or spec.get("arguments") or spec.get("parameters") or {}
    return (nombre, args if isinstance(args, dict) else {})


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


class Cancelado(Exception):
    pass


class Agente:
    def __init__(self, proveedor, max_pasos: int = 30,
                 confirmar: Callable[[str, dict], bool] | None = None,
                 mostrar: Callable[[str, dict], None] | None = None,
                 resultado: Callable[[str, str], None] | None = None,
                 modo: str = "auto"):
        self.prov = proveedor
        self.max_pasos = max_pasos
        self.confirmar = confirmar or (lambda n, a: True)
        self.mostrar = mostrar or (lambda n, a: None)
        self.resultado = resultado or (lambda n, s: None)
        self.modo_texto = False
        self.historial: list[dict] = []
        self.grupos: set[str] = set()       # grupos de herramientas activados en esta conversación
        self.cancelado = False
        self.modo = modo
        self.compacto = False
        self.configurar_modelo()

    # ── perfil según el modelo ────────────────────────────────────────────
    def configurar_modelo(self) -> None:
        tam = self.prov.tamano_b() if hasattr(self.prov, "tamano_b") else None
        if self.modo == "compacto":
            self.compacto = True
        elif self.modo == "completo":
            self.compacto = False
        else:
            self.compacto = tam is not None and tam <= 10
        self.tamano = tam
        if hasattr(self.prov, "num_ctx"):
            self.prov.num_ctx = equipo.num_ctx_para_ram(equipo.ram_gb())
            self.prov.temperatura = 0.2 if self.compacto else None
            self.prov.pensar = False if self.compacto else None
        self.limite_salida = 6000 if self.compacto else 20000

    def nuevo(self) -> None:
        self.historial = []
        self.grupos = set()

    def cancelar(self) -> None:
        self.cancelado = True

    def reparar(self) -> None:
        """Tras una interrupción: cierra llamadas a herramientas que quedaron sin resultado."""
        respondidas = {m.get("tool_call_id") for m in self.historial if m["role"] == "tool"}
        for m in list(self.historial):
            for c in m.get("tool_calls") or []:
                cid = c.get("id") or c["function"]["name"]
                if cid not in respondidas:
                    self.historial.append({"role": "tool", "tool_call_id": cid, "name": c["function"]["name"],
                                           "content": "[interrumpido por el usuario]"})
        if self.historial and self.historial[-1]["role"] != "assistant":
            self.historial.append({"role": "assistant", "content": "(interrumpido)"})

    # ── prompt ────────────────────────────────────────────────────────────
    def _sistema(self, skill_auto: str) -> str:
        if self.compacto:
            s = SISTEMA_COMPACTO.format(contexto=equipo.contexto())
        else:
            s = SISTEMA_COMPLETO.format(contexto=equipo.contexto(), skills=skills.resumen())
        if skill_auto:
            s += f"\n\nPara este pedido sigue esta guía:\n{skill_auto}\n"
        if self.modo_texto:
            lista = "\n".join(
                f"- {e['function']['name']}({', '.join(e['function']['parameters']['properties'])}): "
                f"{e['function']['description']}" for e in self._esquemas())
            s += PROTOCOLO_TEXTO.format(lista=lista)
        return s

    def _esquemas(self) -> list[dict]:
        return tools.esquemas(self.grupos if self.compacto else None)

    # ── herramientas ──────────────────────────────────────────────────────
    def _correr_tool(self, nombre: str, args: dict) -> str:
        if self.cancelado:
            raise Cancelado()
        self.mostrar(nombre, args)
        t = tools.REGISTRO.get(nombre)
        if t and t.es_riesgosa(args) and not self.confirmar(nombre, args):
            salida = "[cancelado] El usuario NO autorizó esta acción. No la repitas; dile qué no se hizo."
        else:
            salida = tools.limitar(tools.ejecutar(nombre, args), self.limite_salida)
        self.resultado(nombre, salida)
        if self.cancelado:
            raise Cancelado()
        return salida

    # ── loop ──────────────────────────────────────────────────────────────
    def preguntar(self, texto: str) -> str:
        self.cancelado = False
        self.grupos |= tools.grupos_para(texto)
        skill = skills.elegir(texto)
        skill_auto = skill.cuerpo if skill else ""
        if skill:
            self.grupos |= tools.grupos_para(skill.cuerpo + " " + skill.descripcion)
        self.historial.append({"role": "user", "content": texto})
        inicio = len(self.historial)
        insistido = False
        vistos: dict[str, int] = {}

        try:
            for _ in range(self.max_pasos):
                if self.cancelado:
                    raise Cancelado()
                mensajes = [{"role": "system", "content": self._sistema(skill_auto)}] + self.historial
                if self.modo_texto:
                    resp = self.prov.chat(mensajes)
                else:
                    try:
                        resp = self.prov.chat(mensajes, self._esquemas())
                    except ToolsNoSoportadas:
                        self.modo_texto = True
                        continue
                if self.cancelado:
                    raise Cancelado()

                calls = resp.get("tool_calls") or []
                contenido = resp.get("content") or ""

                if calls:
                    self.historial.append({"role": "assistant", "content": contenido, "tool_calls": calls})
                    for c in calls:
                        fn = c["function"]
                        args = _args(fn.get("arguments"))
                        firma = fn["name"] + json.dumps(args, sort_keys=True)
                        vistos[firma] = vistos.get(firma, 0) + 1
                        if vistos[firma] > 2:
                            salida = ("[aviso] Ya hiciste exactamente esta llamada. Usa el resultado que ya "
                                      "tienes y da tu respuesta final, o prueba algo distinto.")
                        else:
                            salida = self._correr_tool(fn["name"], args)
                        self.historial.append({"role": "tool", "tool_call_id": c.get("id") or fn["name"],
                                               "name": fn["name"], "content": salida})
                    continue

                pedido = _leer_bloque(contenido)
                if pedido is not None:
                    nombre, args = pedido
                    self.historial.append({"role": "assistant", "content": contenido})
                    if nombre in tools.REGISTRO:
                        salida = self._correr_tool(nombre, args)
                        self.historial.append({"role": "user", "content": f"[resultado de {nombre}]\n{salida}"})
                    else:
                        motivo = args.get("_error") or f"no existe la herramienta '{nombre}'"
                        validas = ", ".join(e["function"]["name"] for e in self._esquemas())
                        self.historial.append({"role": "user", "content":
                            f"[error] {motivo}. Herramientas válidas: {validas}. "
                            "Vuelve a intentarlo con el formato exacto, o responde sin bloque tool si ya terminaste."})
                    continue

                # Respuesta final. ¿Contestó de memoria algo que exigía actuar?
                uso_tools = any(m["role"] == "tool" or m.get("tool_calls") or
                                str(m.get("content", "")).startswith("[resultado de")
                                for m in self.historial[inicio:])
                if self.compacto and not uso_tools and not insistido and _VERBOS_ACCION.search(texto):
                    insistido = True
                    self.historial.append({"role": "assistant", "content": contenido})
                    self.historial.append({"role": "user", "content":
                        "[Arca] No usaste ninguna herramienta. Este pedido requiere actuar o datos reales: "
                        "llama AHORA a la herramienta adecuada en vez de responder de memoria. "
                        "Si de verdad no hace falta ninguna, repite tu respuesta."})
                    continue

                self.historial.append({"role": "assistant", "content": contenido})
                return contenido or "(sin respuesta)"
        except Cancelado:
            self.reparar()
            return "✋ Detenido."

        return "[Arca] Llegué al límite de pasos. Dime si sigo."
