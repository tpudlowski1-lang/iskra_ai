import unittest
from unittest.mock import Mock

from iskra.assistant.chat import KnowledgeChatService


class PolishLocalIntentTests(unittest.TestCase):
    def test_local_intents_never_access_documents_or_provider(self):
        for question in ("czesc", "Cześć!", "jakie masz funkcje",
                         "Hej, jakie masz funkcje?", "co umiesz",
                         "kim jestes", "jakie masz mozliwosci"):
            with self.subTest(question=question):
                documents, router, policy = Mock(), Mock(), Mock()
                service = KnowledgeChatService(documents, router, policy)
                result = service.answer(object(), question)
                self.assertEqual(result["status"], "answered")
                self.assertFalse(result["grounded"])
                self.assertEqual(result["citations"], [])
                self.assertIn("Iskra AI", result["answer"])
                documents.search_documents.assert_not_called()
                router.generate.assert_not_called()
                policy.allowed_for.assert_not_called()

    def test_document_question_stays_in_tenant_search(self):
        documents, router, policy = Mock(), Mock(), Mock()
        documents.search_documents.return_value = []
        principal = object()
        question = "Jakie funkcje opisano w dokumentach naszej firmy?"
        result = KnowledgeChatService(documents, router, policy).answer(principal, question)
        self.assertEqual(result["status"], "no_sources")
        documents.search_documents.assert_called_once_with(principal, question, limit=5)
        router.generate.assert_not_called()
