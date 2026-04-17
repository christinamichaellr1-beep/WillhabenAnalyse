"""
subprocess_runner.py

Launches and manages the WillhabenAnalyse pipeline as a background subprocess.
"""
import signal
import subprocess
import threading
from typing import Callable


def start_pipeline(
    python_path: str,
    project_dir: str,
    parser_version: str = "v2",
    model: str = "gemma3:27b",
    max_listings: int | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> subprocess.Popen:
    """
    Starts: python_path main.py --once --parser-version=... --model=... [--max-listings=N]
    from project_dir. Stdout/stderr to PIPE.
    If log_callback given, spawns a daemon thread reading stdout lines and calling log_callback.
    Returns the Popen object.
    """
    cmd = [
        python_path,
        "main.py",
        "--once",
        f"--parser-version={parser_version}",
        f"--model={model}",
    ]
    if max_listings is not None:
        cmd.append(f"--max-listings={max_listings}")

    proc = subprocess.Popen(
        cmd,
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge so log_callback sees both streams
        text=True,
    )

    if log_callback is not None:
        def _reader():
            for line in proc.stdout:
                log_callback(line.rstrip("\n"))

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

    return proc


def is_running(proc: subprocess.Popen) -> bool:
    """Returns True if process is still alive."""
    return proc.poll() is None


def stop(proc: subprocess.Popen) -> None:
    """Sends SIGTERM, waits 5s, SIGKILL if still alive."""
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
