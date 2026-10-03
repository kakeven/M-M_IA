"""Regressões do rascunho conversacional e da edição da ficha."""

import tempfile
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from mm_ia import creation
from mm_ia.web import SheetHandler


class CreationChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        override = patch.object(creation, "CREATIONS_DIR", directory)
        override.start()
        self.addCleanup(override.stop)

    def test_conversation_resume_and_manual_edit_rewinds_dependent_stage(self):
        state = creation.start_creation({"descricao": "Herói ágil e investigador", "np": 10})
        identifier = state["id"]
        self.assertEqual(len(state["mensagens"]), 2)

        concept = {
            "conceito": {
                "nome_sugerido": "Vigilante", "resumo": "Investigador veloz",
                "estilo": "Investigação", "prioridades": ["Agilidade"],
                "capacidades_essenciais": ["Investigar"], "suposicoes": [],
            },
            "reservas": {area: 0 for area in creation.AREAS},
            "justificativa": "Começamos pela ideia do personagem.", "pendencias": [],
        }
        with patch.object(creation, "retrieve_summaries", return_value=[]), patch.object(creation, "_ask_json", return_value=concept):
            state = creation.propose_stage(identifier, {
                "revisao": state["revisao"], "instrucao": "Quero um investigador veloz",
            })
        self.assertEqual(state["proposta"]["etapa"], "conceito")
        self.assertEqual(state["mensagens"][-2]["texto"], "Quero um investigador veloz")
        self.assertEqual(creation.get_creation(identifier)["mensagens"], state["mensagens"])

        state = creation.approve_stage(identifier, {"revisao": state["revisao"]})
        self.assertEqual(state["ficha"]["nome"], "Vigilante")
        self.assertEqual(state["etapa_atual"], "habilidades")

        abilities = {"habilidades": {"agilidade": 2}, "justificativa": "Ágil.", "pendencias": []}
        with patch.object(creation, "retrieve_summaries", return_value=[]), patch.object(creation, "_ask_json", return_value=abilities):
            state = creation.propose_stage(identifier, {"revisao": state["revisao"]})
        state = creation.approve_stage(identifier, {"revisao": state["revisao"]})
        self.assertEqual(state["etapa_atual"], "pericias")

        skills = {"pericias": {"atletismo": 2}, "justificativa": "Atleta.", "pendencias": []}
        with patch.object(creation, "retrieve_summaries", return_value=[]), patch.object(creation, "_ask_json", return_value=skills):
            state = creation.propose_stage(identifier, {"revisao": state["revisao"]})
        state = creation.approve_stage(identifier, {"revisao": state["revisao"]})
        self.assertTrue(state["ficha"]["pericias"])

        edited = dict(state["ficha"])
        edited["habilidades"] = {**edited["habilidades"], "agilidade": 3}
        state = creation.edit_creation_sheet(identifier, {
            "revisao": state["revisao"], "ficha": edited,
        })
        self.assertEqual(state["ficha"]["habilidades"]["agilidade"], 3)
        self.assertEqual(state["ficha"]["pericias"], [])
        self.assertEqual(state["etapas"]["pericias"]["status"], "pendente")
        self.assertEqual(state["etapa_atual"], "pericias")
        self.assertEqual(creation.get_creation(identifier)["mensagens"][-1]["papel"], "sistema")

        with self.assertRaises(creation.CreationConflict):
            creation.edit_creation_sheet(identifier, {"revisao": state["revisao"] - 1, "ficha": edited})

    def test_http_serves_chat_and_saves_direct_edit(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), SheetHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def request(method, path, payload=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            body = json.dumps(payload).encode() if payload is not None else None
            headers = {"Content-Type": "application/json"} if body else {}
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            content = response.read().decode("utf-8")
            connection.close()
            return response.status, content

        status, page = request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn('id="creationView"', page)
        status, script = request("GET", "/static/creation.js")
        self.assertEqual(status, 200)
        self.assertIn("saveCreationSheet", script)
        status, body = request("POST", "/api/creations", {"descricao": "Heroína investigadora", "np": 10})
        self.assertEqual(status, 201)
        state = json.loads(body)["criacao"]
        sheet = {**state["ficha"], "nome": "Investigadora"}
        status, body = request("POST", f"/api/creations/{state['id']}/sheet", {
            "revisao": state["revisao"], "ficha": sheet,
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["criacao"]["ficha"]["nome"], "Investigadora")

    def test_power_rules_are_available_from_concept_and_bounded(self):
        state = creation.start_creation({"descricao": "Herói que voa", "np": 10})
        matches = [
            {"nome": "Voo", "documento": "Voo permite deslocamento aéreo. " * 100,
             "fontes": []},
            {"nome": "Voo", "documento": "Duplicado", "fontes": []},
            {"nome": "Inexistente", "documento": "Fora do catálogo", "fontes": []},
        ]
        concept = {
            "conceito": {
                "nome_sugerido": "Voador", "resumo": "Voa", "estilo": "Aéreo",
                "prioridades": [], "capacidades_essenciais": ["Voar"], "suposicoes": [],
            },
            "reservas": {area: 0 for area in creation.AREAS},
            "justificativa": "Voo será planejado.", "pendencias": [],
        }
        with patch.object(creation, "retrieve_summaries", return_value=matches) as retrieve, patch.object(creation, "_ask_json", return_value=concept) as ask:
            creation.propose_stage(state["id"], {"revisao": state["revisao"]})
        context = ask.call_args.kwargs["context"]
        self.assertEqual(retrieve.call_args.args[0], "voar")
        self.assertEqual([row["nome"] for row in context["regras_recuperadas"]], ["Voo"])
        self.assertLessEqual(len(context["regras_recuperadas"][0]["resumo"]), 850)


if __name__ == "__main__":
    unittest.main()
