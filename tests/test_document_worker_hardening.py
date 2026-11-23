import json
import os
import unittest
from unittest.mock import patch

from iskra.documents.parsers import ParsedDocument
from iskra.documents import worker


class FakeConnection:
    def __init__(self):
        self.payload = None
        self.closed = False

    def send_bytes(self, payload):
        self.payload = payload

    def close(self):
        self.closed = True


class ParserWorkerHardeningTests(unittest.TestCase):
    def test_worker_clears_inherited_environment_before_parsing(self):
        connection = FakeConnection()
        observed = {}

        def parse(filename, data):
            observed["environment"] = dict(os.environ)
            return ParsedDocument(
                filename="sample.txt",
                extension=".txt",
                sha256="a" * 64,
                chunks=("sample",),
            )

        with patch.dict(os.environ, {"ISKRA_TEST_SECRET": "must-not-leak"}, clear=True):
            with patch.object(worker, "_apply_worker_limits"):
                with patch.object(worker, "parse_document", side_effect=parse):
                    worker._worker_entry(connection, "sample.txt", b"sample", 5, 256 * 1024 * 1024)

        self.assertNotIn("ISKRA_TEST_SECRET", observed["environment"])
        payload = json.loads(connection.payload.decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertTrue(connection.closed)

    @unittest.skipIf(worker.resource is None, "resource limits unavailable")
    def test_worker_applies_low_file_descriptor_soft_limit(self):
        resource = worker.resource
        with patch.object(resource, "getrlimit", return_value=(1024, 4096)) as getrlimit:
            with patch.object(resource, "setrlimit") as setrlimit:
                with patch.object(os, "umask") as umask:
                    worker._apply_worker_limits(5, 256 * 1024 * 1024)

        getrlimit.assert_called_once_with(resource.RLIMIT_NOFILE)
        self.assertIn(
            unittest.mock.call(resource.RLIMIT_NOFILE, (32, 4096)),
            setrlimit.call_args_list,
        )
        umask.assert_called_once_with(0o077)


if __name__ == "__main__":
    unittest.main(verbosity=2)
