import unittest

from iskra.llm.data_minimization import minimize_outbound_text


class OutboundDataMinimizationTests(unittest.TestCase):
    def test_redacts_common_api_tokens_and_cloud_keys(self):
        value = (
            "github_pat_abcdefghijklmnopqrstuvwxyz123456 "
            "ghp_abcdefghijklmnopqrstuvwxyz123456 "
            "AKIA1234567890ABCDEF ASIA1234567890ABCDEF sk-abcdefghijklmnopqrstuvwxyz123456"
        )
        result = minimize_outbound_text(value)
        self.assertNotIn("github_pat_", result)
        self.assertNotIn("ghp_", result)
        self.assertNotIn("AKIA1234567890ABCDEF", result)
        self.assertNotIn("ASIA1234567890ABCDEF", result)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", result)
        self.assertEqual(result.count("[REDACTED:"), 5)

    def test_redacts_bearer_password_assignment_email_and_iban(self):
        value = (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 "
            "password=very-secret-value-123 contact admin@example.com "
            "IBAN PL61109010140000071219812874"
        )
        result = minimize_outbound_text(value)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", result)
        self.assertNotIn("very-secret-value-123", result)
        self.assertNotIn("admin@example.com", result)
        self.assertNotIn("PL61109010140000071219812874", result)
        self.assertGreaterEqual(result.count("[REDACTED:"), 4)

    def test_redacts_multiline_private_key_and_jwt(self):
        private_key = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.signaturelongenough123"
        result = minimize_outbound_text(private_key + " " + jwt)
        self.assertNotIn("BEGIN PRIVATE KEY", result)
        self.assertNotIn(jwt, result)
        self.assertIn("[REDACTED:PRIVATE_KEY]", result)
        self.assertIn("[REDACTED:JWT]", result)

    def test_regular_text_is_preserved(self):
        value = "Procedura zatwierdzania faktur do 1000 PLN przez lidera zespołu."
        self.assertEqual(minimize_outbound_text(value), value)

    def test_non_string_input_is_rejected(self):
        with self.assertRaises(TypeError):
            minimize_outbound_text(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
