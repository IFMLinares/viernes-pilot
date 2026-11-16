"""Exercise public argument dispatch without starting legacy audio/services."""
import ast
import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class EntrypointTests(unittest.TestCase):
    def dispatch(self, args, legacy):
        path = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(path.read_text())
        entry = tree.body[-1]
        self.assertIsInstance(entry, ast.If)
        code = compile(ast.Module(body=[entry], type_ignores=[]), str(path), "exec")
        with patch("sys.argv", ["main.py", *args]):
            exec(code, {"__name__": "__main__", "main": legacy})

    def test_no_arguments_preserve_legacy_dispatch(self):
        legacy = Mock()
        self.dispatch([], legacy)
        legacy.assert_called_once_with()

    @patch("core.planner.main", return_value=0)
    def test_planner_does_not_call_legacy(self, planner):
        legacy = Mock()
        with self.assertRaises(SystemExit) as result:
            self.dispatch(["--planner"], legacy)
        self.assertEqual(result.exception.code, 0)
        planner.assert_called_once_with()
        legacy.assert_not_called()

    def test_help_documents_flag_without_starting_assistant(self):
        output = io.StringIO()
        legacy = Mock()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as result:
            self.dispatch(["--help"], legacy)
        self.assertEqual(result.exception.code, 0)
        self.assertIn("--planner", output.getvalue())
        legacy.assert_not_called()
