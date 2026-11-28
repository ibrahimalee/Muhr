"""Run the whole Muhr backend in one container: three sellers plus the registry.

Used by deploy/huggingface/Dockerfile, where a Space exposes a single public port. The
sellers listen on localhost only; the registry listens on $PORT (7860 by default) and is the
only thing reachable from outside.

Secrets (admin key, one key per seller) are taken from the environment when set and are
generated for this run otherwise, so a public demo never starts with the development keys.
"""

from __future__ import annotations

import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SELLERS = [
    ("sel_summarizer", "sellers.summarizer.app:app", 8001),
    ("sel_classifier", "sellers.classifier.app:app", 8002),
    ("sel_urdu", "sellers.urdu.app:app", 8003),
]

children: list[subprocess.Popen] = []


def _default(env: dict, name: str, value: str) -> None:
    if not env.get(name, "").strip():
        env[name] = value


def build_env() -> dict:
    env = dict(os.environ)
    port = env.get("PORT", "7860")
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    _default(env, "DEMO_MODE", "true")
    _default(env, "MUHR_PUBLIC_DEPLOY", "true")
    _default(env, "MUHR_TRUST_PROXY", "true")
    _default(env, "MUHR_REGISTRY_BASE_URL", f"http://127.0.0.1:{port}")
    _default(env, "MUHR_REGISTRY_INTERNAL_URL", f"http://127.0.0.1:{port}")
    for sid, _, p in SELLERS:
        short = sid.split("_", 1)[1]
        _default(env, f"MUHR_SELLER_{short.upper()}_URL", f"http://127.0.0.1:{p}")
        _default(env, f"MUHR_SELLER_KEY_{sid.upper()}", secrets.token_hex(32))
    _default(env, "MUHR_ADMIN_KEY", secrets.token_hex(32))
    return env


def wait_for(url: str, name: str, timeout: float = 90.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        for p in children:
            if p.poll() is not None:
                stop_all()
                sys.exit(f"{name}: a process exited while starting (code {p.returncode})")
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    stop_all()
    sys.exit(f"{name} did not become ready at {url}")


def stop_all(*_: object) -> None:
    for p in children:
        if p.poll() is None:
            p.terminate()
    deadline = time.time() + 8
    for p in children:
        try:
            p.wait(max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> None:
    env = build_env()
    port = env.get("PORT", "7860")
    os.chdir(ROOT)
    signal.signal(signal.SIGTERM, lambda *a: (stop_all(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *a: (stop_all(), sys.exit(0)))

    for sid, app, p in SELLERS:
        child_env = dict(env)
        child_env["MUHR_SELLER_ID"] = sid
        child_env["MUHR_SELLER_KEY"] = env[f"MUHR_SELLER_KEY_{sid.upper()}"]
        children.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", app, "--host", "127.0.0.1", "--port", str(p)], env=child_env))
    for sid, _, p in SELLERS:
        wait_for(f"http://127.0.0.1:{p}/health", sid)

    children.append(subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "registry.main:app", "--host", "0.0.0.0", "--port", port, "--proxy-headers"],
        env=dict(env, FORWARDED_ALLOW_IPS="*")))
    wait_for(f"http://127.0.0.1:{port}/health", "registry")
    print(f"Muhr backend is up on port {port}", flush=True)

    # If any process dies, stop everything so the host restarts the container cleanly.
    while True:
        for p in children:
            if p.poll() is not None:
                stop_all()
                sys.exit(f"a Muhr process exited (code {p.returncode})")
        time.sleep(2)


if __name__ == "__main__":
    main()
