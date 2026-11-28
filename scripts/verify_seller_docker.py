"""Docker gate for seller registration.

Builds the seller image, then runs ``sellers.worker`` inside a container with
``--network=none --read-only --cap-drop ALL`` and checks that it can open a sealed
input and return a correctly encrypted, self-consistent result. Prints the image
id to use as ``docker_image_hash`` (and in MUHR_VERIFIED_DOCKER_IMAGE_HASHES).

    MUHR_SELLER_KIND=classifier python scripts/verify_seller_docker.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared import crypto_utils  # noqa: E402


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()


def main() -> None:
    kind = os.getenv("MUHR_SELLER_KIND", "summarizer").strip().lower()
    if kind not in {"summarizer", "classifier"}:
        raise SystemExit("Set MUHR_SELLER_KIND to summarizer|classifier")
    try:
        _run(["docker", "info"])
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"[verify] Docker engine not reachable. Start Docker Desktop and re-run.\n{e}")

    tag = f"muhr/seller-{kind}:latest"
    print(f"[verify] building {tag}")
    _run(["docker", "build", "-t", tag, "-f", f"sellers/{kind}/Dockerfile", "."])
    image_id = _run(["docker", "image", "inspect", tag, "--format", "{{.Id}}"])

    priv, pub = crypto_utils.generate_x25519_keypair()
    key = os.urandom(32)
    job_id = "job_docker_verify"
    plaintext = b"Patient has mild fever and cough. Possible influenza."
    req = {"job_id": job_id, "kind": kind, "sealed_input": crypto_utils.seal(pub, plaintext, job_id),
           "result_key_b64": crypto_utils.b64e(key)}
    env = {**os.environ, "MUHR_SELLER_X25519_PRIVATE_B64": crypto_utils.b64e(priv)}

    print("[verify] running worker with --network=none --read-only --cap-drop ALL")
    r = subprocess.run(["docker", "run", "-i", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
                        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "65534:65534",
                        "--memory", "512m", "--cpus", "1.0", "-e", "MUHR_SELLER_X25519_PRIVATE_B64",
                        tag, "python", "-m", "sellers.worker"],
                       input=json.dumps(req), text=True, capture_output=True, env=env)
    if r.returncode != 0:
        raise SystemExit(f"[verify] container failed\n{r.stdout}\n{r.stderr}")
    out = json.loads(r.stdout)
    result = crypto_utils.decrypt_with_key(key, out["result_ciphertext_b64"], out["result_nonce_b64"],
                                           out["result_tag_b64"], aad=job_id.encode())
    if crypto_utils.hash_result(result) != out["result_hash"]:
        raise SystemExit("[verify] result_hash does not match the decrypted result")
    if crypto_utils.ciphertext_digest(out["result_ciphertext_b64"], out["result_nonce_b64"], out["result_tag_b64"]) != out["ciphertext_hash"]:
        raise SystemExit("[verify] ciphertext_hash mismatch")
    print(json.dumps({"ok": True, "kind": kind, "tag": tag, "docker_image_hash": image_id,
                      "result_hash_prefix": out["result_hash"][:16]}, indent=2))


if __name__ == "__main__":
    main()
