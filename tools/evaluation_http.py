"""Single-process evaluation transport budgets; never installed in the application."""
from contextlib import contextmanager
import json
import math
from pathlib import Path
import signal
import sqlite3
import threading
import time
from unittest.mock import patch

import requests


class BudgetExceeded(RuntimeError):
    """A request reservation or execution exceeded its evaluation budget."""


class Budget:
    def __init__(self, max_requests, deadline, ledger=None, request_timeout=90, binding=""):
        if (type(max_requests) is not int or max_requests < 0
                or not math.isfinite(request_timeout) or request_timeout <= 0
                or not math.isfinite(deadline)):
            raise ValueError("Budgets must be finite and positive.")
        self.max_requests, self.deadline = max_requests, deadline
        self.request_timeout = request_timeout
        self._requests, self.connection = 0, None
        if ledger is not None:
            binding = json.dumps([binding, request_timeout])
            Path(ledger).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(ledger, timeout=0.1)
            try:
                with self.connection:
                    self.connection.execute("CREATE TABLE IF NOT EXISTS budget (singleton INTEGER PRIMARY KEY CHECK(singleton=1), maximum INTEGER, expires REAL, binding TEXT, attempts INTEGER)")
                    self.connection.execute("INSERT OR IGNORE INTO budget VALUES (1, ?, ?, ?, 0)",
                                            (max_requests, time.time() + self.remaining_seconds(), binding))
                maximum, expires, stored_binding, self._requests = self.connection.execute(
                    "SELECT maximum, expires, binding, attempts FROM budget").fetchone()
                if (maximum, stored_binding) != (max_requests, binding):
                    raise ValueError("Ledger configuration differs; use the original budget or a new ledger.")
                self.deadline = min(deadline, time.monotonic() + max(0, expires - time.time()))
            except BaseException:
                self.close()
                raise

    @property
    def requests(self):
        if self.connection is not None:
            self._requests = self.connection.execute("SELECT attempts FROM budget").fetchone()[0]
        return self._requests

    def check(self):
        if self.requests >= self.max_requests:
            raise BudgetExceeded("max_requests")
        if time.monotonic() >= self.deadline:
            raise BudgetExceeded("deadline")

    def remaining_seconds(self):
        return max(0, self.deadline - time.monotonic())

    def reserve(self):
        try:
            if self.connection is not None:
                self.connection.execute("BEGIN IMMEDIATE")
            self.check()
            if self.connection is not None:
                self.connection.execute("UPDATE budget SET attempts=attempts+1")
                self.connection.commit()
            self._requests += 1
        except BaseException:
            if self.connection is not None:
                self.connection.rollback()
            raise

    @contextmanager
    def transport(self, sender=None):
        """Wrap every POST, including continuations and explicitly repeated attempts.

        Planner redirects are disabled and requests.post uses no automatic retry
        adapter. No retries are added here. A reserved attempt may never reach the
        server after interruption; it is deliberately not refunded.
        """
        sender = requests.post if sender is None else sender

        def send(*args, **kwargs):
            self.reserve()
            remaining = self.remaining_seconds()
            seconds = min(self.request_timeout, remaining)
            reason = "deadline" if remaining <= self.request_timeout else "request_timeout"
            kwargs["timeout"] = (min(3, seconds / 2), seconds / 2)
            with hard_timeout(seconds, reason):
                result = sender(*args, **kwargs)
            if self.remaining_seconds() <= 0:
                raise BudgetExceeded("deadline")
            return result

        with patch("core.planner.requests.post", side_effect=send):
            yield

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


@contextmanager
def hard_timeout(seconds, reason):
    """A read timeout alone cannot stop a trickling/stalled HTTP body.

    Fail closed on unsupported hosts/threads rather than claiming a hard bound.
    """
    if (not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread()
            or signal.getitimer(signal.ITIMER_REAL)[0]):
        raise RuntimeError("Hard evaluation deadline unavailable.")
    if seconds <= 0:
        raise BudgetExceeded("deadline")
    previous = signal.getsignal(signal.SIGALRM)

    def expired(*_):
        raise BudgetExceeded(reason)

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
