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
    tamano = "4.7B"

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
        if self.path == "/api/show":
            return self._json(200, {"details": {"parameter_size": Guion.tamano}})
        Guion.recibidos.append(payload)
        if self.path == "/api/chat":
            if Guion.rechazar_tools and "tools" in payload:
                return self._json(400, {"error": "registry.ollama.ai/library/x does not support tools"})
            return self._json(200, {"message": Guion.respuestas.pop(0), "done": True})
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

    def test_bloque_roto_se_corrige(self):
        Guion.rechazar_tools = True
        ruta = str(Path(self.dir) / "hola.txt")
        Guion.respuestas = [
            {"content": '```tool\n{"herramienta": "lista_archivos", "argumentos": {"ruta": "/"}}}\n```'},
            {"content": '```tool\n{"herramienta": "leer_archivo", "argumentos": {"ruta": "%s"}}}\n```' % ruta},
            {"content": "Dice 42."},
        ]
        a = Agente(self.prov())
        self.assertEqual(a.preguntar("lee"), "Dice 42.")
        self.assertIn("no existe la herramienta 'lista_archivos'", Guion.recibidos[2]["messages"][2]["content"]
                      if False else a.historial[2]["content"])
        self.assertIn("secreto 42", a.historial[4]["content"])

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


class TestModoCompacto(Base):
    def nativo(self):
        return providers.OllamaNativo("ollama", self.url.replace("/v1", ""), "", "chico:4b")

    def test_perfil_y_opciones(self):
        Guion.respuestas = [{"content": "hola"}]
        a = Agente(self.nativo())
        self.assertTrue(a.compacto)
        a.preguntar("hola")
        p = Guion.recibidos[0]
        self.assertEqual(p["options"]["temperature"], 0.2)
        self.assertGreaterEqual(p["options"]["num_ctx"], 8192)
        self.assertIs(p["think"], False)
        nombres = {t["function"]["name"] for t in p["tools"]}
        self.assertNotIn("chrome_js", nombres)       # menos opciones para el modelo chico
        self.assertIn("leer_archivo", nombres)
        self.assertIn("Datos reales", p["messages"][0]["content"])

    def test_modelo_grande_ve_todo(self):
        Guion.tamano = "70B"
        try:
            Guion.respuestas = [{"content": "ok"}]
            a = Agente(self.nativo())
            self.assertFalse(a.compacto)
            a.preguntar("hola")
            self.assertIn("chrome_js", {t["function"]["name"] for t in Guion.recibidos[0]["tools"]})
        finally:
            Guion.tamano = "4.7B"

    def test_grupos_y_skill_automatica(self):
        Guion.respuestas = [{"content": "", "tool_calls": [{"function": {"name": "crear_recordatorio",
                             "arguments": {"texto": "pagar luz"}}}]}, {"content": "Listo"}]
        llamadas = []
        tools.REGISTRO["crear_recordatorio"].fn, original = (lambda texto, fecha="": llamadas.append(texto) or "[ok]"), tools.REGISTRO["crear_recordatorio"].fn
        try:
            a = Agente(self.nativo())
            self.assertEqual(a.preguntar("recuérdame pagar la luz mañana"), "Listo")
        finally:
            tools.REGISTRO["crear_recordatorio"].fn = original
        self.assertEqual(llamadas, ["pagar luz"])
        p = Guion.recibidos[0]
        self.assertIn("crear_recordatorio", {t["function"]["name"] for t in p["tools"]})
        self.assertIn("crear_recordatorio(texto, fecha)", p["messages"][0]["content"])   # skill agenda inyectada
        seg = Guion.recibidos[1]["messages"]
        self.assertEqual(seg[-1]["role"], "tool")
        self.assertEqual(seg[-2]["tool_calls"][0]["function"]["arguments"], {"texto": "pagar luz"})

    def test_insiste_si_no_actua(self):
        ruta = str(Path(self.dir) / "hola.txt")
        Guion.respuestas = [{"content": "El archivo dice 99."},
                            {"content": "", "tool_calls": [{"function": {"name": "leer_archivo", "arguments": {"ruta": ruta}}}]},
                            {"content": "Dice 42."}]
        a = Agente(self.nativo())
        self.assertEqual(a.preguntar("lee el archivo hola.txt"), "Dice 42.")
        self.assertIn("No usaste ninguna herramienta", Guion.recibidos[1]["messages"][-1]["content"])

    def test_frena_repeticiones(self):
        c = {"content": "", "tool_calls": [{"function": {"name": "listar_carpeta", "arguments": {"ruta": self.dir}}}]}
        Guion.respuestas = [c, c, c, {"content": "fin"}]
        a = Agente(self.nativo())
        a.preguntar("lista la carpeta")
        self.assertIn("Ya hiciste exactamente esta llamada", Guion.recibidos[3]["messages"][-1]["content"])

    def test_cancelar(self):
        a = Agente(self.nativo(), mostrar=lambda n, x: a.cancelar())
        Guion.respuestas = [{"content": "", "tool_calls": [{"function": {"name": "listar_carpeta", "arguments": {}}}]}]
        self.assertEqual(a.preguntar("lista"), "✋ Detenido.")
        self.assertEqual(a.historial[-1]["role"], "assistant")


class TestAltoNivel(unittest.TestCase):
    def test_organizar_carpeta(self):
        d = Path(tempfile.mkdtemp())
        for n in ("a.jpg", "b.pdf", "c.zip", "d.xyz"):
            (d / n).write_text("x")
        plan = tools.organizar_carpeta(str(d))
        self.assertIn("nada se ha movido", plan)
        self.assertTrue((d / "a.jpg").exists())
        t = tools.REGISTRO["organizar_carpeta"]
        self.assertFalse(t.es_riesgosa({"ruta": str(d), "aplicar": "no"}))
        self.assertTrue(t.es_riesgosa({"ruta": str(d), "aplicar": "si"}))
        tools.organizar_carpeta(str(d), "si")
        self.assertTrue((d / "Imágenes" / "a.jpg").exists())
        self.assertTrue((d / "Otros" / "d.xyz").exists())

    def test_fecha_applescript(self):
        self.assertIn("set month of d to 9", tools._fecha_as("2026-09-25 17:00"))
        with self.assertRaises(ValueError):
            tools._fecha_as("mañana")

    def test_skill_ejecutable(self):
        tools.esquemas()
        self.assertIn("clima", tools.REGISTRO)
        self.assertEqual(tools.REGISTRO["clima"].grupo, "skill_ejecutable")

    def test_elegir_skill(self):
        self.assertEqual(skills.elegir("recuérdame ir al súper").nombre, "agenda")
        self.assertEqual(skills.elegir("¿va a llover mañana?").nombre, "clima")
        self.assertIsNone(skills.elegir("hola, ¿cómo estás?"))


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
        for n in ("investigar", "organizar", "resumir-pestana", "crear-skill", "correo", "agenda", "clima"):
            self.assertIn(n, s)
            self.assertTrue(s[n].descripcion)
            self.assertTrue(s[n].activar, n)
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
