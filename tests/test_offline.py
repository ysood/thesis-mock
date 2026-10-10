"""Offline model-call checks and the shared CLI/UI scripted fixture."""

import unittest
from unittest.mock import patch

from app import llm
from app.schema import Reconciliation
from tests.test_v9 import fake_model, load

class ModelCallTest(unittest.TestCase):
    """The real ask() path, with a LangChain fake chat model instead of an API."""

    def tearDown(self):
        llm.model = self.original

    def setUp(self):
        self.original = llm.model

    def test_bad_json_is_retried(self):
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        fake = FakeListChatModel(responses=["Sure! here it is", '```json\n{"conflicts": [], "summary": "ok"}\n```'])
        llm.model = lambda: fake
        with patch.object(llm, 'model_name', return_value='anthropic:offline'):
            result = llm.ask("test", "retry", Reconciliation, "system", "user")
        self.assertEqual(result.summary, "ok")

    def test_api_failure_returns_none(self):
        def broken():
            raise RuntimeError("no API key")
        llm.model = broken
        self.assertIsNone(llm.ask("test", "fail", Reconciliation, "system", "user"))
