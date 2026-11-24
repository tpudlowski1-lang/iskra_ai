import unittest
from unittest.mock import Mock
from iskra.assistant.chat import KnowledgeChatService

class IdentityTests(unittest.TestCase):
    def test_identity_is_local(self):
        documents, router, policy = Mock(), Mock(), Mock()
        service = KnowledgeChatService(documents, router, policy)
        for question in ("czesc.Kim jesteś i jakie masz możliwości?", "Kim jesteś?", "Co potrafisz?"):
            result = service.answer(Mock(), question)
            self.assertEqual(result["status"], "answered")
            self.assertIn("Iskra AI", result["answer"])
            self.assertFalse(result["grounded"])
            self.assertEqual(result["citations"], [])
        documents.search_documents.assert_not_called()
        router.generate.assert_not_called()
        policy.allowed_for.assert_not_called()

    def test_document_question_keeps_tenant_scope(self):
        documents, router = Mock(), Mock()
        documents.search_documents.return_value = []
        principal = Mock()
        result = KnowledgeChatService(documents, router).answer(principal, "Jaka jest treść umowy?")
        self.assertEqual(result["status"], "no_sources")
        documents.search_documents.assert_called_once_with(principal, "Jaka jest treść umowy?", limit=5)
        router.generate.assert_not_called()
