#!/usr/bin/env bash
# Run a MUHR seller whose *job processing* happens in a network-less container.
#
# The HTTP seller (which must talk to the registry and buyers) runs on the host.
# For every job it starts `docker run --network none --read-only --cap-drop ALL ...
# python -m sellers.worker`; the worker opens the sealed input, runs the offline
# pipeline and returns only the encrypted result. The host process never sees
# plaintext, and the code that does see it has no network to leak it through.
#
# Usage: ./scripts/run_seller_isolated.sh <summarizer|classifier> [port]

set -euo pipefail

KIND="${1:-}"
case "$KIND" in
  summarizer) DEFAULT_PORT=8001 ;;
  classifier) DEFAULT_PORT=8002 ;;
  *) echo "usage: $0 <summarizer|classifier> [port]" >&2; exit 64 ;;
esac
PORT="${2:-$DEFAULT_PORT}"

command -v docker >/dev/null 2>&1 || { echo "docker not on PATH" >&2; exit 127; }
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

IMAGE="muhr/seller-${KIND}:latest"
echo "[muhr] building worker image $IMAGE"
docker build -q -t "$IMAGE" -f "sellers/${KIND}/Dockerfile" . >/dev/null
IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}')"

export MUHR_SELLER_ISOLATION=docker
export MUHR_SELLER_WORKER_IMAGE="$IMAGE"
export MUHR_SELLER_IMAGE_HASH="$IMAGE_ID"
if [[ -z "${MUHR_SELLER_X25519_PRIVATE_B64:-}" ]]; then
  MUHR_SELLER_X25519_PRIVATE_B64="$(python -c 'from shared.crypto_utils import generate_x25519_keypair,b64e; print(b64e(generate_x25519_keypair()[0]))')"
  export MUHR_SELLER_X25519_PRIVATE_B64
fi

echo "[muhr] seller $KIND on :$PORT, jobs run in $IMAGE with --network none (image $IMAGE_ID)"
exec python -m uvicorn "sellers.${KIND}.app:app" --host 127.0.0.1 --port "$PORT"
