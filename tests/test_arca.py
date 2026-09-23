"""Pruebas sin modelo real: un servidor falso estilo OpenAI con respuestas guionadas.

Correr:  python3 -m unittest discover tests
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ARCA_HOME"] = tempfile.mkdtemp()

from arca import providers, skills, tools  # noqa: E402
from arca.agent import Agente  # noqa: E402


class Guion(BaseHTTPRequestHandler):
    respuestas: list = []
    recibidos: list = []
    rechazar_tools = False

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json(200, {"data": [{"id": "text-embed"}, {"id": "modelo-falso"},
                                  {"id": "gratis:free", "pricing": {"prompt": "0", "completion": "0"},
                                   "supported_parameters": ["tools"]}]})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Guion.recibidos.append(payload)
        if Guion.rechazar_tools and "tools" in payload:
            return self._json(400, {"error": "registry.ollama.ai/library/x does not support tools"})
        self._json(200, {"choices": [{"message": Guion.respuestas.pop(0)}]})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Guion)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Guion.respuestas, Guion.recibidos, Guion.rechazar_tools = [], [], False
        self.dir = tempfile.mkdtemp()
        (Path(self.dir) / "hola.txt").write_text("contenido secreto 42")

    def prov(self):
        return providers.OpenAICompat("prueba", self.url, "x", "modelo-falso")


class TestAgente(Base):
    def test_tools_nativas(self):
        ruta = str(Path(self.dir) / "hola.txt")
        Guion.respuestas = [
            {"content": None, "tool_calls": [{"id": "c1", "type": "function",
             "function": {"name": "leer_archivo", "arguments": json.dumps({"ruta": ruta})}}]},
            {"content": "<think>mmm</think>El archivo dice 42."},
        ]
        r = Agente(self.prov()).preguntar("¿qué dice hola.txt?")
        self.assertEqual(r, "El archivo dice 42.")
        tool_msg = Guion.recibidos[1]["messages"][-1]
        self.assertEqual(tool_msg["role"], "tool")
        self.assertIn("secreto 42", tool_msg["content"])
        self.assertIn("tools", Guion.recibidos[0])

    def test_fallback_texto(self):
        Guion.rechazar_tools = True
        ruta = str(Path(self.dir) / "hola.txt")
        Guion.respuestas = [
            {"content": '```tool\n{"herramienta": "leer_archivo", "argumentos": {"ruta": "%s"}}\n```' % ruta},
            {"content": "Dice 42."},
        ]
        a = Agente(self.prov())
        self.assertEqual(a.preguntar("lee hola.txt"), "Dice 42.")
        self.assertTrue(a.modo_texto)
        self.assertIn("secreto 42", Guion.recibidos[-1]["messages"][-1]["content"])

    def test_confirmacion_negada(self):
        destino = str(Path(self.dir) / "nuevo.txt")
        Guion.respuestas = [
            {"content": "", "tool_calls": [{"id": "c1", "type": "function",
             "function": {"name": "escribir_archivo", "arguments": json.dumps({"ruta": destino, "contenido": "x"})}}]},
            {"content": "Ok, no lo escribí."},
        ]
        a = Agente(self.prov(), confirmar=lambda n, args: False)
        a.preguntar("escribe")
        self.assertFalse(Path(destino).exists())
        self.assertIn("[cancelado]", Guion.recibidos[1]["messages"][-1]["content"])

    def test_reparar_tras_interrupcion(self):
        a = Agente(self.prov())
        a.historial = [{"role": "user", "content": "hola"},
                       {"role": "assistant", "content": "", "tool_calls": [
                           {"id": "c9", "type": "function", "function": {"name": "terminal", "arguments": "{}"}}]}]
        a.reparar()
        self.assertEqual(a.historial[2]["tool_call_id"], "c9")
        self.assertEqual(a.historial[-1]["role"], "assistant")

    def test_modelo_auto_y_gratis(self):
        p = self.prov()
        self.assertEqual(providers.elegir_modelo_auto(p), "modelo-falso")  # descarta embeddings
        p.nombre = "openrouter"
        self.assertEqual(providers.elegir_modelo_auto(p), "gratis:free")


class TestAnthropic(unittest.TestCase):
    def test_conversion(self):
        msgs = [{"role": "system", "content": "sis"}, {"role": "user", "content": "hola"},
                {"role": "assistant", "content": "voy", "tool_calls": [
                    {"id": "t1", "type": "function", "function": {"name": "terminal", "arguments": '{"comando": "ls"}'}},
                    {"id": "t2", "type": "function", "function": {"name": "listar_carpeta", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "t1", "content": "a"},
                {"role": "tool", "tool_call_id": "t2", "content": "b"}]
        system, out = providers.Anthropic.convertir(msgs)
        self.assertEqual(system, "sis")
        self.assertEqual([m["role"] for m in out], ["user", "assistant", "user"])
        self.assertEqual(out[1]["content"][1]["input"], {"comando": "ls"})
        self.assertEqual([b["tool_use_id"] for b in out[2]["content"]], ["t1", "t2"])


class TestSkillsYTools(unittest.TestCase):
    def test_skills_del_repo(self):
        s = skills.cargar()
        for n in ("investigar", "organizar-carpeta", "resumir-pestana", "crear-skill", "borrador-correo", "recordatorios"):
            self.assertIn(n, s)
            self.assertTrue(s[n].descripcion)
        self.assertIn("Skill: investigar", tools.usar_skill("investigar"))

    def test_skill_nueva(self):
        f = skills.nueva("prueba-x")
        self.assertTrue(f.exists())
        self.assertIn("prueba-x", skills.cargar())

    def test_esquemas_validos(self):
        for e in tools.esquemas():
            f = e["function"]
            self.assertTrue(f["name"] and f["description"])
            for r in f["parameters"]["required"]:
                self.assertIn(r, f["parameters"]["properties"])

    def test_terminal_y_mac_fuera_de_mac(self):
        self.assertIn("hola", tools.terminal("echo hola"))
        if not tools.ES_MAC:
            self.assertIn("solo funciona en macOS", tools.applescript("beep"))


if __name__ == "__main__":
    unittest.main()
