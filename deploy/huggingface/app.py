"""Hugging Face Space entry point (Gradio SDK) for the Muhr backend.

The free Gradio Space type runs any Python program, so this file does not use Gradio at all. It:

1. downloads the Muhr source from GitHub (the repository must be public),
2. installs the backend's pinned requirements into its own virtual environment, so they cannot
   clash with the packages the Space ships with,
3. replaces itself with ``scripts/run_space.py``, which starts the three sellers and the registry
   on port 7860, the only port a Space exposes.

Variables (Space settings): MUHR_REPO_URL and MUHR_REPO_REF choose another fork or branch;
MUHR_CORS_ALLOW_ORIGINS lists the dashboard's origin(s).
"""

import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HOME = os.path.expanduser("~")
REPO_URL = os.getenv("MUHR_REPO_URL", "https://github.com/ibrahimalee/muhr").strip().removesuffix(".git").rstrip("/")
REPO_REF = os.getenv("MUHR_REPO_REF", "main").strip()
CODE_DIR = os.path.join(HOME, "muhr-src")
VENV_DIR = os.path.join(HOME, "muhr-venv")
DATA_DIR = os.path.join(HOME, "data")


def log(msg: str) -> None:
    print(f"[muhr-space] {msg}", flush=True)


def download_source() -> None:
    url = f"{REPO_URL}/archive/refs/heads/{REPO_REF}.zip"
    log(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    tmp = CODE_DIR + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        top = z.namelist()[0].split("/")[0]
        z.extractall(tmp)
    shutil.rmtree(CODE_DIR, ignore_errors=True)
    os.replace(os.path.join(tmp, top), CODE_DIR)
    shutil.rmtree(tmp, ignore_errors=True)


def venv_python() -> str:
    sub = "Scripts" if os.name == "nt" else "bin"
    return os.path.join(VENV_DIR, sub, "python.exe" if os.name == "nt" else "python")


def install_requirements() -> None:
    py = venv_python()
    if not os.path.exists(py):
        log("creating virtual environment")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    log("installing requirements")
    subprocess.check_call([py, "-m", "pip", "install", "--no-cache-dir", "--quiet",
                           "-r", os.path.join(CODE_DIR, "registry", "requirements.txt")])


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isdir(os.path.join(CODE_DIR, "registry")):
        download_source()
    install_requirements()
    env = dict(os.environ)
    env.setdefault("PORT", "7860")
    env.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(DATA_DIR, "muhr.db").replace(os.sep, "/"))
    log("starting the backend")
    os.chdir(CODE_DIR)
    os.execve(venv_python(), [venv_python(), os.path.join("scripts", "run_space.py")], env)


if __name__ == "__main__":
    main()
