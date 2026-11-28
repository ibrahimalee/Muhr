## Seller registration Docker gate (Track C)

Muhr treats seller onboarding as **verification-first**: a seller should only be registered in the registry after proving their container can run under isolation.

### What the gate verifies

The demo gate is implemented by `scripts/verify_seller_docker.py`. It:

- Builds the seller image from the repo.
- Runs it with the required isolation flags:
  - `--network=none`
  - `--read-only`
  - `--tmpfs /tmp:size=512m,noexec`
  - `--memory=2g`
  - `--cpus=2`
  - `--rm`
- Sends an encrypted `SellerJobRequest` on stdin to `python -m sellers.worker`.
- Confirms the container returns a valid `SellerJobResponse` JSON on stdout, and that `result_hash` matches the bytes of `result_b64`.
- Prints a JSON object including `docker_image_hash` (the image ID, `sha256:...`) to use during registry registration.

### Demo onboarding flow (Windows)

1) Start Docker Desktop (Linux containers).

2) Start the registry in **demo mode** (so localhost seller URLs are allowed):

```bash
cmd /c "set DEMO_MODE=true&& python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000"
```

3) Run the verification (summarizer is the default):

```bash
python scripts/verify_seller_docker.py
```

To verify classifier instead:

```bash
set MUHR_SELLER_KIND=classifier
python scripts/verify_seller_docker.py
```

4) Register the verified seller to the registry (this script *runs verify first* and then calls the registry):

```bash
python scripts/register_verified_seller.py
```

5) Confirm it shows up:

- Registry: `GET /api/sellers` returns it as `active`
- Dashboard: refresh `/sellers` to see it in the directory

### Notes / rationale

- This repo uses **Option 1 (demo gate)** from the Muhr “real-first completion” plan: verification happens before calling `POST /api/sellers/register`.
- A fully registry-enforced docker gate (Option 2) requires the registry host to have Docker engine access *and* a way to fetch the seller image deterministically (e.g., a registry URL), which is not part of the current `SellerRegisterRequest` contract.

