import unittest
from unittest.mock import MagicMock, patch

from core.ollama_runtime import ensure_ollama


class RuntimeTests(unittest.TestCase):
    def response(self, models=("qwen3.5:9b",)):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"models": [{"name": name} for name in models]}
        return response

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_reuses_running_server_without_start(self, get, popen):
        get.return_value = self.response()
        self.assertTrue(ensure_ollama("http://127.0.0.1:11434", "qwen3.5:9b", autostart=True).ready)
        popen.assert_not_called()
        self.assertIn("timeout", get.call_args.kwargs)

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_disabled_does_not_start(self, get, popen):
        import requests
        get.side_effect = requests.ConnectionError()
        self.assertFalse(ensure_ollama("http://localhost:11434", "qwen3.5:9b").ready)
        popen.assert_not_called()

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_starts_only_loopback_default_port_and_waits(self, get, popen):
        import requests
        get.side_effect = [requests.ConnectionError(), self.response()]
        popen.return_value.poll.return_value = None
        result = ensure_ollama("http://127.0.0.1:11434", "qwen3.5:9b", autostart=True)
        self.assertTrue(result.ready)
        self.assertEqual(popen.call_args.args[0], ["ollama", "serve"])
        self.assertNotIn("shell", popen.call_args.kwargs)
        self.assertEqual(popen.call_args.kwargs["env"]["OLLAMA_HOST"], "127.0.0.1:11434")

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_remote_url_is_never_probed_or_started(self, get, popen):
        for url in ("http://example.com:11434", "http://0.0.0.0:11434", "http://localhost:8080"):
            self.assertFalse(ensure_ollama(url, "qwen3.5:9b", autostart=True).ready)
        get.assert_not_called()
        popen.assert_not_called()

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_missing_model_does_not_start_or_download(self, get, popen):
        get.return_value = self.response(())
        result = ensure_ollama("http://localhost:11434", "missing", autostart=True)
        self.assertFalse(result.ready)
        self.assertIn("not installed", result.message)
        popen.assert_not_called()

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_timeout_and_missing_binary_leave_offline_mode(self, get, popen):
        import requests
        get.side_effect = requests.ConnectionError()
        popen.side_effect = FileNotFoundError()
        self.assertFalse(ensure_ollama("http://localhost:11434", "m", autostart=True).ready)
        popen.side_effect = None
        popen.return_value.poll.return_value = None
        self.assertFalse(ensure_ollama("http://localhost:11434", "m", autostart=True, wait_seconds=0).ready)
        popen.return_value.terminate.assert_called_once()

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_failed_child_exits_without_unbounded_retry(self, get, popen):
        import requests
        get.side_effect = requests.ConnectionError()
        popen.return_value.poll.return_value = 1
        result = ensure_ollama("http://localhost:11434", "m", autostart=True)
        self.assertFalse(result.ready)
        self.assertIn("exited", result.message)
        self.assertEqual(get.call_count, 2)

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_invalid_timeout_and_redirect_are_not_accepted(self, get, popen):
        self.assertFalse(ensure_ollama("http://localhost:11434", "m", wait_seconds=float("nan")).ready)
        get.assert_not_called()
        get.return_value = self.response()
        get.return_value.status_code = 302
        self.assertFalse(ensure_ollama("http://localhost:11434", "m").ready)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        popen.assert_not_called()

    @patch("core.ollama_runtime.subprocess.Popen")
    @patch("core.ollama_runtime.requests.get")
    def test_owned_child_timeout_escalates_without_shell(self, get, popen):
        import requests
        import subprocess
        get.side_effect = requests.ConnectionError()
        child = popen.return_value
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("ollama", 2), 0]
        status = ensure_ollama("http://127.0.0.1:11434", "qwen3.5:9b", autostart=True, wait_seconds=0)
        self.assertFalse(status.ready)
        self.assertEqual(popen.call_args.args, (["ollama", "serve"],))
        self.assertFalse(popen.call_args.kwargs.get("shell", False))
        child.terminate.assert_called_once_with()
        child.kill.assert_called_once_with()
        self.assertEqual(child.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
