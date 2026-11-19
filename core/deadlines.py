"""Pure hard wall-time guard shared by opt-in runtime and evaluation infrastructure."""
from contextlib import contextmanager
import signal
import threading


@contextmanager
def deadline(seconds, expired, unavailable):
    """Never override another timer or claim enforcement on unsupported hosts."""
    if (not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread()
            or signal.getitimer(signal.ITIMER_REAL)[0]):
        raise unavailable()
    if seconds <= 0:
        raise expired()
    previous = signal.getsignal(signal.SIGALRM)

    def timed_out(*_):
        raise expired()

    signal.signal(signal.SIGALRM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
