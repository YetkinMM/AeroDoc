import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from openai import APITimeoutError, RateLimitError

from scripts.answering import (
    INPUT_FRAMING_ALLOWANCE, USD_UNITS, AnswerError, AnswerService, Ledger, encode,
)
from scripts.ask_api import create_app
from scripts.openai_answers import OpenAIProvider
from scripts.retrieval import ROOT, read


def output(answer="", citations=(), insufficient=False):
    return json.dumps(dict(answer=answer, citations=list(citations),
                           insufficient_evidence=insufficient))


class AnswerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "ledger.sqlite3"
        self.settings = read(ROOT / "config/answers.json")
        self.provider = Mock()
        self.usage = {"input_tokens": 100, "output_tokens": 20,
                      "output_tokens_details": {"reasoning_tokens": 0}}
        self.provider.generate.return_value = (output("Claim [S1].", ["S1"]), self.usage)
        self.searcher = Mock()
        self.searcher.search.return_value = [
            {"text": "Passage", "chunk_id": "chunk-a", "pdf_pages": [1], "printed_pages": ["i"]}
        ]
        self.service = self.make_service()

    def make_service(self, budget="0.50"):
        return AnswerService(self.searcher, self.provider, self.settings, Ledger(self.path, budget),
                             {"retrieval": "bm25"})

    def test_answer_metadata_and_cache(self):
        live = self.service.ask("Question?")
        self.assertEqual(live["status"], "answered")
        self.assertEqual(live["sources"][0]["chunk_id"], "chunk-a")
        self.assertEqual(live["sources"][0]["printed_pages"], ["i"])
        self.assertEqual(live["usage"], self.usage)
        self.searcher.search.assert_called_with("Question?", 5)
        request = self.provider.generate.call_args.args[0]
        self.assertEqual(request["max_output_tokens"], 1200)
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(set(json.loads(request["input"])["passages"][0]),
                         {"label", "chunk_id", "text"})
        cached = self.make_service().ask("Question?")
        self.assertEqual(cached["origin"], "cache")
        self.assertEqual(cached["estimated_cost_usd"], "0")
        self.provider.generate.assert_called_once()
        self.searcher.search.return_value[0]["text"] = "Updated passage"
        self.assertEqual(self.service.ask("Question?")["origin"], "live")

    def test_invalid_output_and_attributions(self):
        cases = [
            ("{", "invalid_output"),
            (output("Claim [S9].", ["S9"]), "invalid_citations"),
            (output("Uncited claim.", ["S1"]), "invalid_citations"),
            (output("Uncited claim."), "invalid_citations"),
            (output("Claim [S1].", ["S1"], True), "invalid_citations"),
        ]
        for raw, code in cases:
            with self.subTest(code=code, raw=raw):
                self.provider.generate.return_value = raw, self.usage
                result = self.service.ask("Question?")
                self.assertEqual((result["status"], result["error_code"]), ("provider_error", code))
                self.assertEqual(result["usage"], self.usage)

    def test_insufficient_evidence(self):
        self.provider.generate.return_value = output(insufficient=True), self.usage
        result = self.service.ask("Question?")
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["sources"], [])

    def test_timeout_persists_reservation_and_prevents_provider_call_after_restart(self):
        self.provider.generate.side_effect = AnswerError("timeout")
        first = self.make_service("0.0015").ask("First?")
        self.assertEqual(first["error_code"], "timeout")
        self.assertTrue(first["reservation_retained"])
        second = self.make_service("0.0015").ask("Second?")
        self.assertEqual(second["status"], "budget_exceeded")
        self.provider.generate.assert_called_once()

    def test_small_budget_never_calls_provider(self):
        self.assertEqual(self.make_service("0.0006").ask("Question?")["status"], "budget_exceeded")
        self.provider.generate.assert_not_called()

    def test_reservation_uses_prepared_request_and_maximum_output(self):
        first = self.service.ask("Question?")
        request = self.provider.generate.call_args.args[0]
        inputs = len(encode(request).encode("utf-8")) + INPUT_FRAMING_ALLOWANCE
        self.assertEqual(first["input_upper_bound"], inputs)
        self.assertEqual(first["output_upper_bound"], 1200)
        self.assertEqual(self.service.cost(inputs, 1200), inputs * 125_000 + 600_000_000)
        self.assertEqual(self.service.cost(1_050_000, 1200), USD_UNITS * 2634 // 10_000)
        self.assertEqual(first["estimated_cost_usd"], "0.0000225")

    def test_previous_charge_and_uncertain_reservation_keep_budget_gate(self):
        self.service.ledger.reserve(USD_UNITS * 499 // 1000, {"previous": True})
        self.provider.generate.side_effect = AnswerError("connection_error")
        first = self.service.ask("First?")
        self.assertTrue(first["reservation_retained"])
        self.assertEqual(self.make_service().ask("Second?")["status"], "budget_exceeded")
        self.provider.generate.assert_called_once()

    def test_local_preflight_has_no_charge(self):
        self.provider.generate.side_effect = AnswerError("api_key_missing_or_invalid", request_sent=False)
        result = self.service.ask("First?")
        self.assertEqual(result["origin"], "none")
        self.assertEqual(result["estimated_cost_usd"], "0")
        self.assertFalse(result["reservation_retained"])
        self.provider.generate.side_effect = None
        self.assertEqual(self.make_service().ask("Second?")["status"], "answered")

    def test_health_validation_and_provider_http_errors(self):
        with TestClient(create_app(self.service)) as client:
            self.assertEqual(client.get("/health").json(), {"status": "ok", "retrieval": "bm25"})
            for value in (" ", "x" * 2001, 123):
                self.assertEqual(client.post("/ask", json={"question": value}).status_code, 422)
            self.provider.generate.assert_not_called()
            self.assertEqual(client.post("/ask", json={"question": "Question?"}).status_code, 200)
        for code, http in [("rate_limit", 503), ("output_token_limit", 502), ("refusal", 502),
                           ("incomplete_output", 502), ("timeout", 504)]:
            with self.subTest(code=code), TestClient(create_app(self.service)) as client:
                self.provider.generate.side_effect = AnswerError(code, self.usage)
                response = client.post("/ask", json={"question": code})
                self.assertEqual(response.status_code, http)
                self.assertEqual(response.json()["status"], "provider_error")
                self.assertEqual(response.json()["error_code"], code)
        with TestClient(create_app(self.make_service("0.0006"))) as client:
            response = client.post("/ask", json={"question": "Budget?"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json()["error_code"], "budget_exceeded")

    @patch("scripts.openai_answers.dotenv_values", return_value={"OPENAI_API_KEY": "test-key"})
    @patch("scripts.openai_answers.OpenAI")
    def test_transport_maps_rate_limit_timeout_refusal_and_truncation(self, sdk, env):
        provider = OpenAIProvider(self.settings)
        send = sdk.return_value.__enter__.return_value.responses.create
        http_request = Mock()
        http_response = Mock(status_code=429, request=http_request)
        usage = Mock()
        usage.model_dump.return_value = self.usage
        cases = [
            (APITimeoutError(request=http_request), None, "timeout"),
            (RateLimitError("rate", response=http_response, body={"code": "rate_limit_exceeded"}),
             None, "rate_limit"),
            (None, SimpleNamespace(status="incomplete", usage=usage,
                                   incomplete_details=SimpleNamespace(reason="max_output_tokens")),
             "output_token_limit"),
            (None, SimpleNamespace(status="completed", usage=usage,
                                   output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal")])]),
             "refusal"),
        ]
        for error, response, code in cases:
            with self.subTest(code=code), self.assertRaises(AnswerError) as caught:
                send.side_effect = error
                send.return_value = response
                provider.generate({"input": "Question?"})
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(caught.exception.usage, self.usage if response else None)
        self.assertEqual(sdk.call_args.kwargs["max_retries"], 0)
