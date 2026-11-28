"""Hugging Face Space entry point (Gradio SDK, free ZeroGPU type) for the Muhr backend.

A Space exposes one port, and the free Gradio type expects a Gradio app. This file serves both:

* the public port (7860) runs a small FastAPI app. It forwards ``/api/*`` and ``/health`` to the
  real Muhr backend and shows a status page (Gradio) everywhere else;
* in the background it downloads the Muhr source from GitHub (the repository must be public),
  installs the backend's pinned requirements into its own virtual environment, and runs
  ``scripts/run_space.py`` on an internal port. That script starts the three sellers and the registry.

Nothing here uses a GPU. ``spaces`` is imported and one placeholder function is decorated because a
ZeroGPU Space refuses to start without one. The function is never called.

Variables (Space settings): MUHR_CORS_ALLOW_ORIGINS lists the dashboard's origin(s);
MUHR_REPO_URL and MUHR_REPO_REF choose another fork or branch.
"""

# `spaces` must be imported before anything that touches CUDA.
try:
    import spaces

    _gpu = spaces.GPU(duration=10)
except ImportError:  # running outside a Space (local test)

    def _gpu(fn):
        return fn


import io
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

import gradio as gr
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

HOME = os.path.expanduser("~")
REPO_URL = os.getenv("MUHR_REPO_URL", "https://github.com/ibrahimalee/muhr").strip().removesuffix(".git").rstrip("/")
REPO_REF = os.getenv("MUHR_REPO_REF", "main").strip()
CODE_DIR = os.path.join(HOME, "muhr-src")
VENV_DIR = os.path.join(HOME, "muhr-venv")
DATA_DIR = os.path.join(HOME, "data")
PUBLIC_PORT = int(os.getenv("MUHR_PUBLIC_PORT", "7860"))
BACKEND_PORT = int(os.getenv("MUHR_BACKEND_PORT", "8000"))

ready = threading.Event()
state = {"message": "Starting"}


def log(msg: str) -> None:
    state["message"] = msg
    print(f"[muhr-space] {msg}", flush=True)


# ---------------------------------------------------------------- backend (background)

def download_source() -> None:
    url = f"{REPO_URL}/archive/refs/heads/{REPO_REF}.zip"
    log(f"Downloading {url}")
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
        log("Creating virtual environment")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    log("Installing requirements")
    subprocess.check_call([py, "-m", "pip", "install", "--no-cache-dir", "--quiet",
                           "-r", os.path.join(CODE_DIR, "registry", "requirements.txt")])


def start_backend() -> subprocess.Popen:
    env = dict(os.environ)
    env["PORT"] = str(BACKEND_PORT)
    env.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(DATA_DIR, "muhr.db").replace(os.sep, "/"))
    return subprocess.Popen([venv_python(), os.path.join("scripts", "run_space.py")], cwd=CODE_DIR, env=env)


def backend_ok() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/health", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def run_backend_forever() -> None:
    """Download, install, start, and restart the backend if it ever exits."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isdir(os.path.join(CODE_DIR, "registry")):
            download_source()
        install_requirements()
    except Exception as e:  # noqa: BLE001
        log(f"Setup failed: {e}")
        return
    delay = 5
    while True:
        log("Starting the backend")
        proc = start_backend()
        deadline = time.time() + 120
        while time.time() < deadline and proc.poll() is None and not backend_ok():
            time.sleep(1)
        if proc.poll() is None and backend_ok():
            ready.set()
            log("Running")
            delay = 5
            while proc.poll() is None:
                time.sleep(3)
        ready.clear()
        if proc.poll() is None:
            proc.terminate()
        log(f"Backend stopped (code {proc.poll()}); restarting in {delay}s")
        time.sleep(delay)
        delay = min(delay * 2, 60)


# ---------------------------------------------------------------- public app

HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
              "transfer-encoding", "upgrade", "host", "content-length"}
client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=None, write=60.0, pool=None))
app = FastAPI(title="Muhr backend (Space front door)", docs_url=None, redoc_url=None, openapi_url=None)


async def forward(request: Request, path: str):
    if not ready.is_set():
        return JSONResponse({"detail": "The Muhr backend is starting. Try again in a minute."}, status_code=503,
                            headers={"Access-Control-Allow-Origin": "*", "Retry-After": "20"})
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
    # The registry rate-limits per client address and trusts only the last X-Forwarded-For hop,
    # which here is the address the Space's own gateway saw.
    xff = request.headers.get("x-forwarded-for", "")
    headers["x-forwarded-for"] = (xff.split(",")[-1].strip() if xff else (request.client.host if request.client else "unknown"))
    upstream = client.build_request(request.method, f"http://127.0.0.1:{BACKEND_PORT}/{path}",
                                    params=request.query_params, headers=headers, content=await request.body())
    try:
        r = await client.send(upstream, stream=True)
    except httpx.HTTPError:
        return JSONResponse({"detail": "The Muhr backend is not reachable right now."}, status_code=502,
                            headers={"Access-Control-Allow-Origin": "*"})
    out = {k: v for k, v in r.headers.items() if k.lower() not in HOP_BY_HOP}
    return StreamingResponse(r.aiter_raw(), status_code=r.status_code, headers=out, background=BackgroundTask(r.aclose))


METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


async def api_proxy(request: Request, path: str):
    return await forward(request, "api/" + path)


async def health_proxy(request: Request):
    return await forward(request, "health")


app.add_api_route("/api/{path:path}", api_proxy, methods=METHODS)
app.add_api_route("/health", health_proxy, methods=METHODS)


@_gpu
def _zerogpu_placeholder() -> str:
    """Never called. A ZeroGPU Space will not start unless one function carries the GPU decorator."""
    return "unused"


def status() -> str:
    if ready.is_set():
        return "The Muhr backend is running. The dashboard talks to `/api` on this address."
    return f"The Muhr backend is not ready yet: {state['message']}."


with gr.Blocks(title="Muhr backend") as demo:
    gr.Markdown("# Muhr backend\nThe registry and three demo sellers (summarizer, classifier, Urdu translation), "
                "in demo mode: invoices are synthetic and no money moves.\n\n"
                "- Health: `/health`\n- Sellers: `/api/sellers`\n- Live feed: `/api/feed`\n\n"
                "Source: https://github.com/ibrahimalee/muhr")
    out = gr.Markdown(status)
    gr.Button("Refresh status").click(status, outputs=out)
    hidden = gr.Button(visible=False)
    hidden.click(_zerogpu_placeholder, outputs=gr.Textbox(visible=False))

try:
    app = gr.mount_gradio_app(app, demo, path="/", ssr_mode=False)
except TypeError:
    app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    threading.Thread(target=run_backend_forever, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=PUBLIC_PORT, proxy_headers=True, forwarded_allow_ips="*")
