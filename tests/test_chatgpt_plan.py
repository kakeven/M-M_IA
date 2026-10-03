"""Formato de requisição e diagnóstico de erros da conexão ChatGPT."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mm_ia import chatgpt_plan


class ChatGPTPlanTests(unittest.TestCase):
    def _client(self, events=None, error=None):
        client = MagicMock()
        if error is not None:
            client.responses.create.side_effect = error
        else:
            client.responses.create.return_value.__enter__.return_value = events or [
                SimpleNamespace(type="response.output_text.delta", delta='{"ok":true}'),
                SimpleNamespace(type="response.completed"),
            ]
        return client

    def test_json_instruction_is_in_input_and_effort_is_optional(self):
        client = self._client()
        with patch.object(chatgpt_plan, "_access_token", return_value="test-token"), patch.object(
            chatgpt_plan, "OpenAI", return_value=client,
        ):
            self.assertTrue(chatgpt_plan.ask_json("Instruções", "Crie um herói", "gpt-6-astra")["ok"])
            payload = client.responses.create.call_args.kwargs
            self.assertIn("JSON", payload["input"][0]["content"])
            self.assertIn("Crie um herói", payload["input"][0]["content"])
            self.assertNotIn("reasoning", payload)

            chatgpt_plan.ask_json("Instruções", "Crie um herói", "gpt-5.6-terra", "low")
            self.assertEqual(client.responses.create.call_args.kwargs["reasoning"], {"effort": "low"})

    def test_bad_input_is_not_reported_as_effort_error(self):
        failure = Exception("invalid request")
        failure.status_code = 400
        failure.body = {"type": "invalid_request_error", "param": "input"}
        client = self._client(error=failure)
        with patch.object(chatgpt_plan, "_access_token", return_value="test-token"), patch.object(
            chatgpt_plan, "OpenAI", return_value=client,
        ):
            with self.assertRaisesRegex(RuntimeError, "formato da mensagem"):
                chatgpt_plan.ask_json("Instruções", "Pedido", "gpt-6-astra")

    def test_rejects_unsupported_effort_before_request(self):
        with self.assertRaisesRegex(ValueError, "nenhum"):
            chatgpt_plan.ask_json("Instruções", "Pedido", "gpt-6-astra", "none")
        with self.assertRaisesRegex(ValueError, "máximo"):
            chatgpt_plan.ask_json("Instruções", "Pedido", "gpt-5.5", "max")

    def test_subscription_limit_is_not_reported_as_connection_error(self):
        failure = Exception("usage limit")
        failure.body = {"code": "subscription_sharing_usage_limit_exceeded"}
        client = self._client(error=failure)
        with patch.object(chatgpt_plan, "_access_token", return_value="test-token"), patch.object(
            chatgpt_plan, "OpenAI", return_value=client,
        ):
            with self.assertRaisesRegex(RuntimeError, "Limite do ChatGPT Plus atingido"):
                chatgpt_plan.ask_json("Instruções", "Pedido", "gpt-6-astra")


if __name__ == "__main__":
    unittest.main()
