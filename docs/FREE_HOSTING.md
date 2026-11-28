# Free hosting: dashboard on Vercel, backend on a Hugging Face Space

The dashboard is a static site, so Vercel hosts it. The registry and the three sellers need a
long-running process, so they run together in one Space on Hugging Face. Both have a free
plan and neither asks for a card. The deployment runs in **demo mode**: invoices are synthetic and no
money moves.

```
 browser ──► Vercel (dashboard, static)
    │
    └──────► Hugging Face Space (registry on :7860, sellers on localhost)
```

## 1. Backend on Hugging Face

The free Space type is **Gradio**. It runs any Python program, so a small `app.py` downloads this
repository, installs the pinned requirements into its own virtual environment and starts the
backend. (Docker Spaces are a paid option on some accounts; a Dockerfile for them is in
[`deploy/huggingface-docker/`](../deploy/huggingface-docker/).)

1. Create an account at huggingface.co, then **New Space**: any name, **SDK: Gradio**, template
   **Blank**, hardware **CPU basic (free)**, visibility **Public**.
2. In the Space, **Files → Add file → Upload files**, and upload the two files from
   [`deploy/huggingface/`](../deploy/huggingface/): `app.py` and `README.md`. Replace the template's
   own `app.py` and `README.md`. The README header tells Hugging Face to run `app.py` on Python 3.11.
3. **Settings → Variables and secrets**, add a **variable**:

   | Name | Value |
   | --- | --- |
   | `MUHR_CORS_ALLOW_ORIGINS` | your Vercel address, e.g. `https://muhr.vercel.app` (comma-separate several) |

   Optional **secrets**: `GROQ_API_KEY` and `GEMINI_API_KEY` for real AI answers. Leave them out and
   the sellers use the built-in offline pipeline. The admin key and seller keys are generated on every
   start; set `MUHR_ADMIN_KEY` and `MUHR_SELLER_KEY_SEL_SUMMARIZER`, `_SEL_CLASSIFIER`, `_SEL_URDU`
   as secrets only if you want fixed values.
4. The Space starts (the first start takes a couple of minutes: it downloads the code and installs
   the packages; watch **Logs**). When it says *Running*, open
   `https://<user>-<space>.hf.space/health`. It should answer `{"status":"healthy",...}`.
   Check `/api/sellers` too: three active sellers.

`app.py` hands over to `scripts/run_space.py`, which starts the three sellers on localhost, then the
registry on the public port, and exits if any of them stops so Hugging Face restarts it. To run a
fork or another branch, set the variables `MUHR_REPO_URL` and `MUHR_REPO_REF`.

## 2. Dashboard on Vercel

1. At vercel.com, **Add New → Project**, import the GitHub repository.
2. Set **Root Directory** to `front-end/muhr-nexus`. The framework (Vite), build command and output
   folder come from `vercel.json`.
3. Add an **environment variable**: `VITE_API_BASE_URL` = `https://<user>-<space>.hf.space` (no
   trailing slash).
4. Deploy. Direct links such as `/receipt/<job_id>` and `/?pitch=1` work because `vercel.json`
   falls back to `index.html`.

If the Vercel address changes (custom domain, new project), update `MUHR_CORS_ALLOW_ORIGINS` on the
Space; the Space restarts when a variable changes.

## 3. Check it

Open the Vercel address: the Overview, Jobs, Sellers and Volume pages should fill with sample data.
Open `/?pitch=1`, run a preset, and watch the eight stages light up. In the job's receipt, **Verify**
should show a green seal.

## What to expect from the free plans

- **Sleeping.** A Space with no visitors for a couple of days goes to sleep; the next visit wakes it
  in about a minute. Open it before a demo.
- **Data resets.** The disk is not permanent, so the database is recreated when the Space restarts,
  with the built-in sample data. Jobs from earlier sessions are gone.
- **No per-job containers.** Docker is not available inside a Space, so the optional isolated worker
  (`MUHR_SELLER_ISOLATION=docker`) is off. Jobs run in-process.
- **Public repository.** `app.py` downloads the code from GitHub, so the repository must be public.
- **Slow restarts.** Every start downloads the code and installs packages again (about two minutes).
- **Real Lightning payments** are not part of this setup. See [`WALLET_FUNDING.md`](WALLET_FUNDING.md).
