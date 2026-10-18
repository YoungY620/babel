"""A shared wall-clock deadline for Ubuntu pipeline process trees."""
import math
import os
import signal
import subprocess
import time
from contextlib import contextmanager


class BudgetExpired(BaseException):
    """Control flow: ordinary network retry handlers must not swallow the deadline."""


def remaining(deadline):
    seconds = float(deadline) - time.time()
    if not math.isfinite(seconds) or seconds <= 0:
        raise BudgetExpired('Cycle work budget exhausted; completed checkpoints are retained')
    return seconds


def run_command(command, *, deadline=None, env=None, capture=False):
    deadline = deadline if deadline is not None else os.environ.get('BABEL_PROCESS_DEADLINE')
    timeout = remaining(deadline) if deadline is not None else None
    process = None
    try:
        blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        try:
            process = subprocess.Popen(command, env=env, start_new_session=True,
                                       stdout=subprocess.PIPE if capture else None,
                                       stderr=subprocess.PIPE if capture else None, text=True)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked)
        stdout, stderr = process.communicate(timeout=timeout)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        raise BudgetExpired('Stage reached the cycle deadline') from None
    finally:
        # Include ffmpeg, worker pools and any descendants left after their parent exits.
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


@contextmanager
def work_deadline(deadline):
    seconds = remaining(deadline)
    previous = signal.getsignal(signal.SIGALRM)
    timer = signal.getitimer(signal.ITIMER_REAL)
    def expired(*_):
        raise BudgetExpired('Cycle work budget exhausted; completed checkpoints are retained')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *timer)
        signal.signal(signal.SIGALRM, previous)
