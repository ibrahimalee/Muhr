# Deploying Muhr on one server (docker compose + Caddy)

This puts the whole stack on a single Linux VPS: the registry, the three sellers (summarizer, classifier, Urdu) and the dashboard behind HTTPS. A public deployment runs in **DEMO mode**: invoices are synthetic and no money moves.

## 1. Server

A small VPS is enough (1 vCPU, 1 GB RAM, Ubuntu 22.04 or newer), with ports **80** and **443** open and a DNS `A` record pointing your domain at its IP.

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker
git clone <your repository url> muhr && cd muhr
```

## 2. Configuration (`.env`)

Create `.env` in the repository root. **Never commit it** (it is git-ignored). Generate each secret with `openssl rand -hex 32`.

```bash
# Mode: a public deployment is DEMO, and says so.
DEMO_MODE=true
# Make the registry and sellers refuse to start without the keys below.
MUHR_PUBLIC_DEPLOY=true

# Secrets (all four are required when MUHR_PUBLIC_DEPLOY=true)
MUHR_ADMIN_KEY=<openssl rand -hex 32>
MUHR_SELLER_KEY_SEL_SUMMARIZER=<openssl rand -hex 32>
MUHR_SELLER_KEY_SEL_CLASSIFIER=<openssl rand -hex 32>
MUHR_SELLER_KEY_SEL_URDU=<openssl rand -hex 32>

# Browser origin(s) allowed to call the API directly. Same-origin through nginx needs none.
MUHR_CORS_ALLOW_ORIGINS=https://muhr.example.com

# Optional: real AI providers for the sellers (leave empty for the offline pipeline).
# Hosted providers see the decrypted input.
GROQ_API_KEY=
GEMINI_API_KEY=

# Optional: shown only if the rate API has never answered.
MUHR_FALLBACK_BTC_PKR=25000000

# Use another port than 80 if Caddy runs on the same host (see step 3).
MUHR_COMPOSE_PORT=8081
```

### Variables that must be set for a public DEMO deployment

| Variable | Why |
| --- | --- |
| `DEMO_MODE=true` | No sats move; synthetic invoices |
| `MUHR_PUBLIC_DEPLOY=true` | Turns off the well-known development keys and the open admin endpoints |
| `MUHR_ADMIN_KEY` | Protects approval decisions and stake crediting; the registry will not start without it |
| `MUHR_SELLER_KEY_SEL_SUMMARIZER`, `_SEL_CLASSIFIER`, `_SEL_URDU` | Shared secret between the registry and each seller; each process will not start without its key |
| `MUHR_CORS_ALLOW_ORIGINS` | Only needed if a browser on another origin calls the API |

If any required key is missing the container exits at startup with `Refusing to start ... set <name>`. The same checks apply whenever `DEMO_MODE=false`.

## 3. Start the stack

```bash
docker compose up -d --build
docker compose ps                      # registry, summarizer, classifier, urdu, web: all "running"
```

The compose file publishes the dashboard on `MUHR_COMPOSE_PORT` and proxies `/api`, `/health` and the live feed to the registry. Direct links such as `/receipt/<job_id>` and `/?pitch=1` work because nginx falls back to `index.html` for any path that is not a file.

## 4. HTTPS with Caddy

Install Caddy (see caddyserver.com/docs/install), then create `/etc/caddy/Caddyfile`:

```
muhr.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8081 {
        flush_interval -1      # lets the live event stream through unbuffered
    }
}
```

```bash
sudo systemctl reload caddy
```

Caddy gets and renews the certificate on its own. Set `MUHR_TRUST_PROXY` only if you also terminate TLS elsewhere; the compose file already trusts the nginx hop in front of the registry.

## 5. Check it works

```bash
curl https://muhr.example.com/health          # {"status":"healthy",...}
curl https://muhr.example.com/api/sellers     # three active sellers
curl https://muhr.example.com/api/rates       # "source": "coingecko" (or "fallback" with "stale": true)
```

Open `https://muhr.example.com/?pitch=1`, press **Hire a seller**, and run a preset: all eight stages should light up, and the job should appear in the ledger with a **View receipt** link. In the receipt, **Verify** should show a green seal.

## 6. Updating and backups

```bash
git pull && docker compose up -d --build
docker run --rm -v muhr_muhr_registry_data:/data -v "$PWD":/backup alpine tar czf /backup/muhr-db.tgz -C /data .
```

The registry's SQLite database lives in the `muhr_registry_data` volume; new columns are added automatically on start.

For the hardened seller container, seller verification and nginx notes, see [`DEPLOY_REGISTRY.md`](DEPLOY_REGISTRY.md).
