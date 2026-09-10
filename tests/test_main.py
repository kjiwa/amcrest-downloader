import unittest
from unittest.mock import MagicMock, patch

import main


class TestMain(unittest.TestCase):
    @patch("main.CLI")
    def test_main_delegates_to_cli_run(self, mock_cli_cls):
        mock_cli = MagicMock()
        mock_cli.run.return_value = 0
        mock_cli_cls.return_value = mock_cli

        result = main.main()
        self.assertEqual(result, 0)
        mock_cli.run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
