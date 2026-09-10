import logging
import tempfile
import unittest
from pathlib import Path

from logger import configure_logging, get_logger


class TestLogger(unittest.TestCase):
    def tearDown(self):
        for handler in logging.getLogger().handlers:
            handler.close()
        logging.getLogger().handlers = []
        logging.disable(logging.CRITICAL)

    def test_get_logger(self):
        log = get_logger("test_module")
        self.assertEqual(log.name, "test_module")

    def test_configure_logging_console(self):
        configure_logging("info")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.INFO)
        self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in root.handlers))

    def test_configure_logging_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            configure_logging("debug", log_file=log_file)
            root = logging.getLogger()
            self.assertEqual(root.level, logging.DEBUG)
            self.assertTrue(any(isinstance(h, logging.FileHandler) for h in root.handlers))


if __name__ == "__main__":
    unittest.main()
