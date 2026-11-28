# Deploying the MUHR Registry (public internet)

This doc is a practical checklist for deploying the FastAPI **registry** and ensuring the **MUHR Nexus (or any browser UI) SSE feed** works reliably behind a proxy.

## What you deploy

- **Registry**: `registry/main.py` (FastAPI, serves `/api/*` including `/api/feed` SSE)
- **UI**: `front-end/muhr-nexus/` (Vite; proxies to the registry in dev, or set `VITE_API_BASE_URL` in production)

## Required environment variables

### Registry

- **`DEMO_MODE`**: `true|false`
  - `false` for production-like behavior.

- **`MUHR_CORS_ALLOW_ORIGINS`**: comma-separated origins allowed to call the registry from a browser.
  - Example: `https://dashboard.example.com,https://admin.example.com`
  - Use `*` only if you explicitly want public cross-origin access (not recommended).

- **`MUHR_RATE_LIMIT_REGISTER_PER_MIN`** (default `10`)
  - Per-IP limit for `POST /api/sellers/register`.

- **`MUHR_RATE_LIMIT_APPROVE_PER_MIN`** (default `60`)
  - Per-IP limit for `POST /api/approve`.

#### Public seller registration safety (recommended)

When `DEMO_MODE=false`, the registry **will reject unverified docker images by default**.

- **`MUHR_VERIFIED_DOCKER_IMAGE_HASHES`**: comma-separated allowlist of docker image hashes that are permitted to register.
  - Example: `sha256:aaaaaaaa...,sha256:bbbbbbbb...`

- **`MUHR_ALLOW_UNVERIFIED_SELLERS`**: `true|false` (default `false`)
  - Set to `true` only for controlled demos. This removes the allowlist requirement.

### MUHR Nexus (Vite)

- **`VITE_API_BASE_URL`**: full base URL of the public registry (no path), e.g. `https://registry.example.com` — for static builds and when you do not use a same-origin reverse proxy.

## SSE behind a reverse proxy (nginx / cloud load balancer)

SSE can silently fail if buffering is enabled. You want:

- no response buffering
- long-lived connections allowed
- timeouts raised

### Nginx example

```nginx
location /api/feed {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Connection "";
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_buffering off;
  proxy_cache off;
  proxy_read_timeout 3600s;
}
```

The registry also sends `X-Accel-Buffering: no` to help with nginx defaults.

## Deployment notes

- **Render/Railway/Fly/VPS**: all work; pick what your team is already using.
- **Docker required?** Not for the registry itself. Docker is only required if you later enforce seller Docker verification *inside* the registry host.

## Endpoints worth highlighting in production

In addition to the core registration / task / settle paths, the registry now exposes:

- `POST /api/jobs/{job_id}/payment` — receives the on-network Lightning payment proof from the buyer MCP. The body shape is `{lightning_payment_hash, amount_sats, mode}`. The proof is persisted on the `Job` row and emitted on the SSE feed as `lightning_paid`. Make sure your reverse proxy doesn't strip the `Authorization` header on this route.
- `POST /api/sellers/{seller_id}/stake` and `POST /api/sellers/{seller_id}/unstake` — stake top-ups and withdrawals. They write `Stake` and `Transaction` rows and emit `stake_deposited` / `stake_withdrawn` events. Rate-limit them at the proxy if you expose them publicly.
- `GET /api/buyer/wallet` — read-only proxy to the buyer's MDK wallet for the Nexus UI. Best left **internal**; gate with a network-level ACL or behind same-origin only.

## L402 paywall on sellers (optional)

Sellers return every result encrypted, together with a per-job invoice and an HMAC-signed L402 macaroon. After paying, the buyer unlocks the result key at `POST /key`, either with `Authorization: L402 <macaroon>:<preimage_hex>` or by letting the seller confirm the payment in its own MDK wallet. When you deploy this:

- Set a stable `MUHR_L402_SECRET` and `MUHR_SELLER_X25519_PRIVATE_B64` that are shared by every replica of a seller. Otherwise a macaroon or sealed input from one replica can't be used on another.
- Set `MUHR_SELLER_KEY` on the seller and the matching `MUHR_SELLER_KEY_<SELLER_ID>` on the registry. Both are required outside DEMO.
- Set `MUHR_ADMIN_KEY` on the registry (approval decisions and stake credits) and `MUHR_TRUST_PROXY=true` only when your own reverse proxy is in front.

## Hardened seller container

The privacy property requires sellers to run with no outbound network and a read-only filesystem. Use the helper scripts in `scripts/run_seller_isolated.{ps1,sh}` — they apply `--rm --read-only --tmpfs /tmp --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=128 --memory=512m`, plus `--network=none` when invoked with `--no-network` / `-NoNetwork`.

## Full stack with Docker (registry + both sellers + Nexus UI)

From the **repository root**, with [Docker](https://docs.docker.com/get-docker/) installed:

```bash
docker compose up --build
```

- Open **http://localhost** (port **80**). If 80 is in use, set `MUHR_COMPOSE_PORT=8080` and use **http://localhost:8080**).
- The **web** service serves the Vite build and proxies `/api/*` and `/health` to the registry (same-origin; no `VITE_API_BASE_URL` needed in the image).
- SQLite and migrations live in the **`muhr_registry_data`** named volume.
- For a **VPS** with a domain and HTTPS (e.g. Caddy or nginx in front of port 80/443), set in `.env` or the host environment, for example:
  - `MUHR_REGISTRY_BASE_URL=https://your.domain` (public origin users see; updates seeded seller rows)
  - `MUHR_CORS_ALLOW_ORIGINS=https://your.domain` if the UI is on another origin
  - `DEMO_MODE=false` when you want production-like rules

## Quick validation checklist

- `GET /health` returns 200.
- MUHR Nexus (or your browser client) loads and shows feed activity.
- Browser DevTools → Network → `feed` shows streaming frames including `lightning_paid` rows after a real run.
- `POST /api/sellers/register`:
  - In `DEMO_MODE=false`: rejects unverified image unless allowlisted.
  - In `DEMO_MODE=true`: usable for local demos.
- `python -m pytest tests/` (registry slash + payment recording) passes.

