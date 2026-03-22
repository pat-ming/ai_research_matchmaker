"""
Start script: launches the FastAPI backend and Next.js frontend together.

Usage:
    python main.py          # Start both servers
    python main.py api      # Start only the API server
    python main.py web      # Start only the Next.js dev server
"""

import shutil
import subprocess
import sys
import os
import signal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
API_SCRIPT = PROJECT_ROOT / "api" / "server.py"
WEB_DIR = PROJECT_ROOT / "research-matchmaker"

# Use the same python that's running this script, falling back to python3
PYTHON = sys.executable or shutil.which("python3") or "python3"


def start_api():
    """Start the FastAPI server."""
    print(f"Starting API server on http://localhost:8000  (using {PYTHON})")
    return subprocess.Popen(
        [PYTHON, str(API_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        # Give each child its own process group so we can kill the whole tree
        preexec_fn=os.setsid,
    )


def start_web():
    """Start the Next.js dev server."""
    print("Starting Next.js dev server on http://localhost:3000 ...")
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(WEB_DIR),
        preexec_fn=os.setsid,
    )


def kill_procs(procs: list[subprocess.Popen]):
    """Kill all child process groups."""
    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "both"
    procs: list[subprocess.Popen] = []

    if cmd in ("both", "api"):
        procs.append(start_api())
    if cmd in ("both", "web"):
        procs.append(start_web())

    if not procs:
        print(f"Unknown command: {cmd}")
        print("Usage: python main.py [api|web|both]")
        sys.exit(1)

    print("\nServers running. Press Ctrl+C to stop.\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        kill_procs(procs)
        print("Done.")


if __name__ == "__main__":
    main()
