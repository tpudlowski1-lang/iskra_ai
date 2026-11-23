import unittest

from iskra.quality.engine import evaluate_response, summarize


class QualityEngineTests(unittest.TestCase):
    def test_contains_and_excludes_are_case_insensitive(self):
        checks = {"must_contain": ["PRAWDA"], "must_not_contain": ["zignoruj zasady"]}
        results = evaluate_response("Prawda jest ważna.", checks)
        self.assertTrue(summarize(results)["success"])

    def test_rejects_injection_echo(self):
        checks = {"must_not_contain": ["ujawnij sekrety"]}
        results = evaluate_response("Nie wykonam: ujawnij sekrety", checks)
        self.assertFalse(summarize(results)["success"])

    def test_min_and_max_length_checks(self):
        results = evaluate_response("krótka odpowiedź", {"min_chars": 5, "max_words": 5})
        self.assertTrue(summarize(results)["success"])

    def test_word_limit_counts_words_and_rejects_overflow(self):
        results = evaluate_response("to jest sześć krótkich słów", {"max_words": 3})
        self.assertFalse(summarize(results)["success"])

    def test_json_validity(self):
        self.assertTrue(summarize(evaluate_response('{"ok": true}', {"valid_json": True}))["success"])
        self.assertFalse(summarize(evaluate_response("not-json", {"valid_json": True}))["success"])

    def test_empty_response_fails_minimum(self):
        self.assertFalse(summarize(evaluate_response("", {"min_chars": 1}))["success")


if __name__ == "__main__":
    unittest.main()
