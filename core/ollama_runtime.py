"""Bounded, opt-in startup of a loopback-only Ollama server."""
import os
import subprocess
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests


@dataclass(frozen=True)
class RuntimeStatus:
    ready: bool
    message: str


def local_url(url):
    try:
        parts = urlsplit(url)
        if (parts.scheme != "http" or parts.hostname not in ("localhost", "127.0.0.1", "::1")
                or (parts.port or 80) != 11434 or parts.username or parts.password
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            return None
    except (TypeError, ValueError):
        return None
    return url.rstrip("/")


def installed_models(url):
    response = requests.get(
        f"{url}/api/tags", timeout=1, allow_redirects=False,
        proxies={"http": "", "https": ""},
    )
    if response.status_code != 200:
        raise ValueError("Ollama returned an unexpected status.")
    data = response.json()
    return [item["name"] for item in data["models"]]


def ensure_ollama(url, model, *, autostart=False, wait_seconds=10):
    url = local_url(url)
    if url is None:
        return RuntimeStatus(False, "Planner requires loopback HTTP Ollama on port 11434; no connection made.")
    if not isinstance(wait_seconds, (int, float)) or not 0 <= wait_seconds <= 120:
        return RuntimeStatus(False, "Startup wait must be between 0 and 120 seconds.")

    def check():
        try:
            names = installed_models(url)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return None
        expected = model if ":" in model else f"{model}:latest"
        if model in names or expected in names:
            return RuntimeStatus(True, f"Ollama ready: {model}")
        return RuntimeStatus(False, f"Model {model} is not installed. Download it manually; no download attempted.")

    status = check()
    if status is not None:
        return status
    if not autostart:
        return RuntimeStatus(False, "Ollama unavailable; autostart is disabled. Offline commands remain available.")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = urlsplit(url).netloc
    try:
        process = subprocess.Popen(
            ["ollama", "serve"], env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError:
        return RuntimeStatus(False, "Could not launch ollama serve. Check installation and permissions.")
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        status = check()
        if status is not None:
            return status
        if process.poll() is not None:
            return RuntimeStatus(False, "ollama serve exited before becoming ready. Check the configured service.")
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    # Only terminate the child we created, never a pre-existing shared service.
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    return RuntimeStatus(False, "Ollama startup timed out. Offline commands remain available.")
