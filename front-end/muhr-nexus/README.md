# Muhr dashboard

The web dashboard for the Muhr registry: live jobs, sellers, volume and a protocol walkthrough.

## Run it

```sh
npm install
npm run dev     # http://localhost:8080
```

The registry must be running on port 8000 (`python -m uvicorn registry.main:app --port 8000` from the repo root). In development, `/api` and `/health` are proxied to it. For a static build, set `VITE_API_BASE_URL` to the registry's public URL.

## Scripts

- `npm run build` builds into `dist/`.
- `npm test` runs the unit tests.
- `npm run lint` runs ESLint.

The Spline 3D layer is off by default in every build, development and production. It only appears (and its runtime is only downloaded) when `VITE_SPLINE_SCENE` is explicitly set to a scene URL.

Open `/?pitch=1` (or press `P`) for the single-screen pitch layout, and `/receipt/<job_id>` for a job's public receipt.
