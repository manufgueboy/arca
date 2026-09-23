"""Proveedores de modelos.

Formato interno de mensajes = estilo OpenAI:
  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [{"id", "type": "function", "function": {"name", "arguments": str}}],
   "tool_call_id": str}

- OpenAICompat cubre Ollama, LM Studio, OpenRouter, Groq, Gemini, OpenAI y
  cualquier servidor compatible.
- Anthropic traduce a/desde el API de Messages de Claude.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import config as cfgmod


class ProveedorError(RuntimeError):
    pass


class ToolsNoSoportadas(ProveedorError):
    """El modelo no acepta herramientas nativas → el agente usa modo texto."""


_PISTAS_SIN_TOOLS = ("does not support tools", "tool use", "tools is not supported",
                     "tool_choice", "function calling", "no endpoints found that support tool")


def _http(url: str, payload: dict | None, headers: dict, timeout: int = 600) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "arca/0.1", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="replace")[:800]
        raise ProveedorError(f"HTTP {e.code}: {cuerpo}") from e
    except urllib.error.URLError as e:
        raise ProveedorError(f"No pude conectar con {url} ({e.reason}). "
                             "¿Está corriendo el servidor / hay internet?") from e


def _limpiar(texto: str) -> str:
    # Algunos modelos (qwen3, deepseek-r1) meten su razonamiento en <think>.
    return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.DOTALL).strip()


class OpenAICompat:
    def __init__(self, nombre: str, base_url: str, api_key: str, modelo: str):
        self.nombre, self.base_url, self.api_key, self.modelo = nombre, base_url.rstrip("/"), api_key, modelo

    def _headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if self.nombre == "openrouter":
            h.update({"HTTP-Referer": "https://github.com/manufgueboy/arca", "X-Title": "Arca"})
        return h

    def chat(self, mensajes: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict = {"model": self.modelo, "messages": mensajes}
        if tools:
            payload["tools"] = tools
        try:
            r = _http(f"{self.base_url}/chat/completions", payload, self._headers())
        except ProveedorError as e:
            if tools and any(p in str(e).lower() for p in _PISTAS_SIN_TOOLS):
                raise ToolsNoSoportadas(str(e)) from e
            raise
        if "choices" not in r:
            raise ProveedorError(f"Respuesta inesperada: {str(r)[:500]}")
        m = r["choices"][0]["message"]
        return {"role": "assistant", "content": _limpiar(m.get("content") or ""),
                "tool_calls": m.get("tool_calls") or []}

    def listar_modelos(self) -> list[dict]:
        r = _http(f"{self.base_url}/models", None, self._headers(), timeout=30)
        salida = []
        for m in r.get("data", []):
            gratis = False
            precio = m.get("pricing")
            if isinstance(precio, dict):
                gratis = str(precio.get("prompt")) in ("0", "0.0") and str(precio.get("completion")) in ("0", "0.0")
            tools = "tools" in (m.get("supported_parameters") or ["tools"])
            salida.append({"id": m["id"], "gratis": gratis or m["id"].endswith(":free"), "tools": tools})
        return salida


class Anthropic:
    VERSION = "2023-06-01"

    def __init__(self, nombre: str, base_url: str, api_key: str, modelo: str):
        self.nombre, self.base_url, self.api_key, self.modelo = nombre, base_url.rstrip("/"), api_key, modelo

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "anthropic-version": self.VERSION}

    @staticmethod
    def convertir(mensajes: list[dict]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m["content"] for m in mensajes if m["role"] == "system")
        salida: list[dict] = []

        def agregar(rol: str, bloques: list[dict]) -> None:
            if salida and salida[-1]["role"] == rol:
                salida[-1]["content"].extend(bloques)
            else:
                salida.append({"role": rol, "content": list(bloques)})

        for m in mensajes:
            if m["role"] == "user":
                agregar("user", [{"type": "text", "text": m["content"] or "(vacío)"}])
            elif m["role"] == "assistant":
                bloques = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                for tc in m.get("tool_calls") or []:
                    args = tc["function"].get("arguments") or "{}"
                    bloques.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                                    "input": json.loads(args) if isinstance(args, str) else args})
                agregar("assistant", bloques or [{"type": "text", "text": "…"}])
            elif m["role"] == "tool":
                agregar("user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"],
                                  "content": m["content"] or "(sin salida)"}])
        return system, salida

    def chat(self, mensajes: list[dict], tools: list[dict] | None = None) -> dict:
        system, msgs = self.convertir(mensajes)
        payload: dict = {"model": self.modelo, "max_tokens": 8192, "messages": msgs}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [{"name": t["function"]["name"], "description": t["function"]["description"],
                                 "input_schema": t["function"]["parameters"]} for t in tools]
        r = _http(f"{self.base_url}/messages", payload, self._headers())
        texto, calls = [], []
        for b in r.get("content", []):
            if b["type"] == "text":
                texto.append(b["text"])
            elif b["type"] == "tool_use":
                calls.append({"id": b["id"], "type": "function",
                              "function": {"name": b["name"], "arguments": json.dumps(b["input"])}})
        return {"role": "assistant", "content": "\n".join(texto).strip(), "tool_calls": calls}

    def listar_modelos(self) -> list[dict]:
        r = _http(f"{self.base_url}/models", None, self._headers(), timeout=30)
        return [{"id": m["id"], "gratis": False, "tools": True} for m in r.get("data", [])]


_NO_CHAT = ("embed", "whisper", "tts", "dall-e", "moderation", "image", "audio", "realtime",
            "transcribe", "search", "guard", "rerank")


def elegir_modelo_auto(prov) -> str:
    """Si el usuario no fijó modelo, toma uno razonable de los disponibles."""
    modelos = [m for m in prov.listar_modelos() if not any(x in m["id"].lower() for x in _NO_CHAT)]
    if not modelos:
        raise ProveedorError(f"'{prov.nombre}' no tiene modelos disponibles. "
                             + ("Instala uno: ollama pull qwen3:8b" if prov.nombre == "ollama" else ""))
    if prov.nombre == "openrouter":
        gratis = [m for m in modelos if m["gratis"] and m["tools"]]
        if gratis:
            return gratis[0]["id"]
    con_tools = [m for m in modelos if m["tools"]]
    return (con_tools or modelos)[0]["id"]


def crear(cfg: dict, nombre: str | None = None, modelo: str | None = None):
    nombre = nombre or cfg["proveedor"]
    todos = cfgmod.proveedores(cfg)
    if nombre not in todos:
        raise ProveedorError(f"Proveedor desconocido '{nombre}'. Opciones: {', '.join(todos)}")
    datos = todos[nombre]
    key = cfgmod.api_key(cfg, nombre, datos)
    if not key and datos.get("env"):
        raise ProveedorError(f"Falta la API key de {nombre}. Corre: arca login {nombre}  "
                             f"(o exporta {datos['env']})")
    clase = Anthropic if datos.get("tipo") == "anthropic" else OpenAICompat
    prov = clase(nombre, datos["base_url"], key, "")
    prov.modelo = modelo or (cfg.get("modelo") if nombre == cfg["proveedor"] else "") or datos.get("modelo") or elegir_modelo_auto(prov)
    return prov
