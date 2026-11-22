import unittest

from iskra.config import load_settings


class RuntimeConfigurationTests(unittest.TestCase):
    def test_defaults_use_project_root_and_valid_port(self):
        settings = load_settings(environ={}, project_root="/tmp/iskra-project")
        self.assertEqual(settings.port, 10000)
        self.assertEqual(settings.data_dir, "/tmp/iskra-project")

    def test_custom_values_are_normalized(self):
        settings = load_settings(
            environ={"PORT": "8080", "DATA_DIR": "/tmp/iskra-data"},
            project_root="/unused",
        )
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.data_dir, "/tmp/iskra-data")

    def test_non_integer_port_is_rejected(self):
        with self.assertRaises(ValueError):
            load_settings(environ={"PORT": "eight"}, project_root="/tmp")

    def test_out_of_range_port_is_rejected(self):
        for value in ("0", "65536", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    load_settings(environ={"PORT": value}, project_root="/tmp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
