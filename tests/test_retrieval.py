"""Testes sintéticos para recuperação híbrida e citações locais."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mm_ia import pipeline


SOURCE = {
    "livro": "Livro de teste",
    "secao": "Seção de teste",
    "pagina_impressa": 12,
    "pagina_pdf": 18,
}


class FakeCollection:
    def get(self, where, include):
        if where["nome"] != "sono":
            return {"ids": [], "documents": [], "metadatas": []}
        return {
            "ids": ["efeito_sono"],
            "documents": ["Resumo sintético do efeito Sono."],
            "metadatas": [
                {
                    "nome": "sono",
                    "tipo": "efeito",
                    "fontes_json": json.dumps([SOURCE]),
                }
            ],
        }

    def query(self, query_texts, n_results, include):
        self.last_query = query_texts[0]
        self.last_n_results = n_results
        return {
            "ids": [["efeito_sono", "efeito_aflicao"]],
            "documents": [
                [
                    "Resumo sintético do efeito Sono.",
                    "Resumo sintético de outro efeito.",
                ]
            ],
            "metadatas": [[
                {"nome": "sono", "tipo": "efeito", "fontes_json": "[]"},
                {"nome": "aflição", "tipo": "efeito", "fontes_json": "[]"},
            ]],
            "distances": [[0.1, 0.3]],
        }


class HybridRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.collection = FakeCollection()
        self.collections_patch = patch.object(
            pipeline, "get_collections", return_value=(None, self.collection)
        )
        self.collections_patch.start()
        self.addCleanup(self.collections_patch.stop)

    def test_exact_matches_precede_semantic_results_and_are_deduplicated(self):
        results = pipeline.retrieve_summaries(
            "quero colocar alguém para dormir",
            [{"efeito": "Sono", "relevancia": 0.9}],
        )

        self.assertEqual(
            [item["id"] for item in results], ["efeito_sono", "efeito_aflicao"]
        )
        self.assertEqual(
            [item["correspondencia"] for item in results], ["exata", "semantica"]
        )
        self.assertIn("colocar alguém para dormir", self.collection.last_query)
        self.assertEqual(self.collection.last_n_results, 2)

    def test_verified_local_source_is_returned(self):
        results = pipeline.retrieve_summaries(
            "Sono", [{"efeito": "Sono", "relevancia": 0.9}]
        )

        self.assertEqual(results[0]["fontes"], [SOURCE])
        self.assertNotIn("referencia", results[0])

    def test_missing_source_is_explicit_and_never_invented(self):
        results = pipeline.retrieve_summaries(
            "Sono", [{"efeito": "Sono", "relevancia": 0.9}]
        )

        self.assertEqual(results[1]["fontes"], [])
        self.assertEqual(results[1]["referencia"], "Fonte não cadastrada")


if __name__ == "__main__":
    unittest.main()
