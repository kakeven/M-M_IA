"""Verificação HTTP da interface manual, com salvamento em pasta temporária."""
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Motor de regras"))
import armazenamento
spec = importlib.util.spec_from_file_location("manual_web", ROOT / "Motor de regras/web.py")
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


class ManualWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web.ManualHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name in ("FICHAS_DIR", "MOTOR_DIR"):
            patcher = patch.object(armazenamento, name, Path(self.temp.name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def request(self, method, path, data=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(data).encode() if data is not None else None
        defaults = {"Content-Type": "application/json"} if body else {}
        connection.request(method, path, body=body, headers={**defaults, **(headers or {})})
        response = connection.getresponse()
        text = response.read().decode()
        status = response.status
        connection.close()
        return status, json.loads(text) if text.startswith(("{", "[")) else text

    def nova(self):
        status, data = self.request("POST", "/api/nova", {"nome": "Herói", "np": 10})
        self.assertEqual(status, 201)
        return data["ficha"]

    def test_arquivos_html_css_js_e_catalogo(self):
        for path, trecho in (("/", 'lang="pt-BR"'), ("/app.css", "@media"), ("/app.js", "/api/salvar")):
            status, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(trecho, body)
        status, data = self.request("GET", "/api/catalogo")
        self.assertEqual(status, 200)
        self.assertIn("efeitos", data)

    def test_editar_salvar_abrir_e_exportar(self):
        ficha = self.nova()
        ficha["habilidades"]["agilidade"] = 3
        ficha["defesas"]["esquiva"] = 7
        ficha["notas"] = "Anotação de teste"
        status, data = self.request("POST", "/api/calcular", {"ficha": ficha})
        self.assertEqual(status, 200)
        self.assertEqual(data["ficha"]["estatisticas"]["defesas"]["esquiva"], 10)
        self.assertEqual(data["ficha"]["pontosDisponiveis"], 137)
        status, saved = self.request("POST", "/api/salvar", {"ficha": ficha, "arquivo": "heroi"})
        self.assertEqual(status, 200)
        self.assertEqual(saved["arquivo"], "heroi.json")
        status, opened = self.request("GET", "/api/ficha?arquivo=heroi.json")
        self.assertEqual(status, 200)
        self.assertEqual(opened["ficha"]["notas"], ficha["notas"])
        status, listing = self.request("GET", "/api/fichas")
        self.assertEqual(len(listing["fichas"]), 1)
        status, exported = self.request("POST", "/api/exportar", {"ficha": ficha})
        self.assertIn("Anotação de teste", exported["texto"])

    def test_rejeita_dados_invalidos_sem_gravar(self):
        ficha = self.nova()
        ficha["np"] = 0
        status, result = self.request("POST", "/api/salvar", {"ficha": ficha, "arquivo": "invalido"})
        self.assertEqual(status, 400)
        self.assertIn("erro", result)
        self.assertFalse(list(Path(self.temp.name).glob("*.json")))

    def test_nao_permite_origem_externa_ou_caminho_arbitrario(self):
        status, _ = self.request("POST", "/api/nova", {}, {"Origin": "https://externo.example"})
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/api/catalogo", headers={"Host": "externo.example"})
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/salvar", {"ficha": self.nova(), "arquivo": "../fora"})
        self.assertEqual(status, 400)
        status, _ = self.request("GET", "/../ficha.py")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
