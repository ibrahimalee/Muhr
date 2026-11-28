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

**Do it in this order.** The dashboard needs the Space's address, and the Space needs the
dashboard's address, so start with a setting that allows any address and tighten it at the end:

1. Create the Space with `MUHR_CORS_ALLOW_ORIGINS` set to `*` (section 1).
2. Deploy the dashboard on Vercel with `VITE_API_BASE_URL` set to the Space address (section 2).
3. Go back to the Space and replace `*` with the real Vercel address (section 3).

## 1. Backend on Hugging Face

Hugging Face has no free normal server hardware for new Gradio or Docker Spaces. The one free
option is **ZeroGPU**, which a free personal account can host (up to 2 Spaces; the account needs a
verified email and must be at least 30 days old). Nothing here uses a GPU, so the app only has to
satisfy ZeroGPU's rules: it is a Gradio app, and it carries one placeholder GPU function that is
never called. (A Dockerfile for accounts that do have Docker Spaces is in
[`deploy/huggingface-docker/`](../deploy/huggingface-docker/).)

1. Log in at huggingface.co, then **New Space**: any name, **SDK: Gradio**, template **Blank**,
   hardware **ZeroGPU** (the free choice), visibility **Public**.
2. In the Space, **Files → Add file → Upload files**, and upload the two files from
   [`deploy/huggingface/`](../deploy/huggingface/): `app.py` and `README.md`. Replace the template's
   own `app.py` and `README.md`. The README header tells Hugging Face to run `app.py` on Python 3.12.
3. **Settings → Variables and secrets**, add these. Variables are visible to anyone who can see the
   Space settings; **secrets** are hidden, so keys always go in secrets.

   | Kind | Name | Value |
   | --- | --- | --- |
   | variable | `MUHR_CORS_ALLOW_ORIGINS` | `*` for now (replaced in section 3) |
   | variable | `LLM_BASE_URL` | the AI provider's address, e.g. `https://api.groq.com/openai/v1` |
   | variable | `LLM_MODEL` | e.g. `openai/gpt-oss-120b` |
   | **secret** | `LLM_API_KEYS` | your keys on one line, separated by commas, no spaces |

   The three `LLM_` settings are optional: leave them out and the sellers use the built-in offline
   pipeline (the Urdu seller then returns a placeholder instead of a real translation). With several
   keys, each job starts on the next key; a key that is rate-limited (HTTP 429) rests for a while, a
   timeout or server error moves on to the next key, and a key the provider rejects is dropped until
   the Space restarts. Hosted AI providers see the decrypted input of every job.
   You can check the same settings from your own machine first with `python scripts/check_llm.py`
   (it never prints a key). The older single `GROQ_API_KEY` and `GEMINI_API_KEY` secrets still work and
   are tried after the list. The admin key and seller keys are generated on every start; set
   `MUHR_ADMIN_KEY` and `MUHR_SELLER_KEY_SEL_SUMMARIZER`, `_SEL_CLASSIFIER`, `_SEL_URDU` as secrets only
   if you want fixed values.
4. The Space starts (the first start takes a couple of minutes: it downloads the code and installs
   the packages; watch **Logs**). When it says *Running*, open
   `https://<user>-<space>.hf.space/health`. It should answer `{"status":"healthy",...}`; until the
   backend is up it answers 503 with a short message. Check `/api/sellers` too: three active sellers.
   The Space's home page is a small status page.

How it works: `app.py` serves the public port. It forwards `/api/*` and `/health` to the real backend
and shows a status page everywhere else. In the background it downloads this repository, installs
the pinned requirements into its own virtual environment, and runs `scripts/run_space.py` on an
internal port; that script starts the three sellers and the registry, and exits if any of them stops.
`app.py` then restarts it. To run a fork or another branch, set the variables `MUHR_REPO_URL` and
`MUHR_REPO_REF`.

## 2. Dashboard on Vercel

1. At vercel.com, **Add New → Project**, import the GitHub repository.
2. Set **Root Directory** to `front-end/muhr-nexus`. The framework (Vite), build command and output
   folder come from `vercel.json`.
3. Add an **environment variable**: `VITE_API_BASE_URL` = `https://<user>-<space>.hf.space` (no
   trailing slash).
4. Deploy. Direct links such as `/receipt/<job_id>` and `/?pitch=1` work because `vercel.json`
   falls back to `index.html`.

Vercel shows the project's address when the deploy finishes, e.g. `https://muhr.vercel.app`.

## 3. Tighten the Space's setting

Back on the Space, **Settings → Variables and secrets**, change `MUHR_CORS_ALLOW_ORIGINS` from `*` to
your Vercel address. To allow several (a custom domain, for example), separate them with commas. The
Space restarts when a variable changes, so wait for *Running* again. Vercel's preview links each have
their own address; if you use them, keep `*` or list each one. The API has no logins or cookies, so
`*` is acceptable for a demo; it only means any website's page may call it.

## 4. Check it

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
