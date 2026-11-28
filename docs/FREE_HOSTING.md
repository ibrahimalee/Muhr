# Free hosting: dashboard on Vercel, backend on a Hugging Face Space

The dashboard is a static site, so Vercel hosts it. The registry and the three sellers need a
long-running process, so they run together in one Space on Hugging Face. Both have a free plan and
neither asks for a card. The deployment runs in **demo mode**: invoices are synthetic and no money
moves.

```
 browser ──► Vercel (dashboard, static)
    │
    └──────► Hugging Face Space (registry on :7860, sellers on localhost)
```

Follow Parts A, B and C in this order. The dashboard needs the Space's address and the Space needs the
dashboard's address, so the Space starts out allowing any address (`*`) and Part C tightens it.

Throughout, `<hf-user>` is your Hugging Face username and `<space>` is the Space's name. The Space's
address is `https://<hf-user>-<space>.hf.space` in lower case (for example user `alice` and Space
`muhr` give `https://alice-muhr.hf.space`). The Space page's **⋮** menu → **Embed this Space** shows
the exact address.

## Part A. The backend on Hugging Face

Hugging Face has no free normal server hardware for new Gradio or Docker Spaces. The one free option
is **ZeroGPU**, which a free personal account can host (up to 2 Spaces; the account needs a verified
email and must be at least 30 days old). Nothing here uses a GPU; the app carries a placeholder GPU
function that is never called, because a ZeroGPU Space will not start without one.

1. Log in at huggingface.co and click **New Space**.
2. Fill in the form: Space name `muhr`, **Space SDK: Gradio**, template **Blank**, **Space hardware:
   ZeroGPU**, **Public**. Click **Create Space**.
3. Open the **Files** tab. Click **Add file → Upload files**. Drag in the two files from the folder
   [`deploy/huggingface/`](../deploy/huggingface/) of this repository: `app.py` and `README.md`. They
   have the same names as the template's files and replace them. Click **Commit changes to main**.
4. Open **Settings**, scroll to **Variables and secrets**, and add the following. A variable is added
   with **New variable**, a secret with **New secret**. Keys always go in a **secret**.

   | Kind | Name | Value |
   | --- | --- | --- |
   | variable | `MUHR_CORS_ALLOW_ORIGINS` | `*` |
   | variable | `LLM_BASE_URL` | `https://api.groq.com/openai/v1` (the AI provider's address) |
   | variable | `LLM_MODEL` | `openai/gpt-oss-120b` |
   | **secret** | `LLM_API_KEYS` | your keys on ONE line, separated by commas, no spaces: `key1,key2,key3` |

   The three `LLM_` rows are optional. Leave them out and the sellers use the built-in offline
   pipeline, where the Urdu seller returns a placeholder instead of a real translation. Hosted AI
   providers see the decrypted input of every job. You can test the same keys on your own computer
   first with `python scripts/check_llm.py`, which never prints a key.
5. Open the **App** tab, then **Logs**. The first start takes about 2 to 3 minutes: it downloads the
   code from GitHub and installs the packages. It is ready when the Space says **Running**.
6. Check it. Open these two addresses in a browser:
   - `https://<hf-user>-<space>.hf.space/health` must show `{"status":"healthy", ...}`.
     While it is still starting it shows a short "starting" message instead; wait and refresh.
   - `https://<hf-user>-<space>.hf.space/api/sellers` must list **three** sellers
     (`sel_summarizer`, `sel_classifier`, `sel_urdu`), all `active`.

   Do not continue until both work.

## Part B. The dashboard on Vercel

1. At vercel.com, click **Add New → Project** and import the GitHub repository.
2. Set **Root Directory** to `front-end/muhr-nexus`. The framework (Vite), build command and output
   folder come from `vercel.json`; leave them as they are.
3. Open **Environment Variables** and add `VITE_API_BASE_URL` with the Space address from Part A,
   with **no `/` at the end**: `https://<hf-user>-<space>.hf.space`.
   **Do this before you click Deploy.** The value is built into the site, so if you add or change it
   later you must click **Redeploy** for it to take effect.
4. Click **Deploy**. When it finishes, Vercel shows the project's address, for example
   `https://muhr.vercel.app`. Open it: the Overview, Jobs, Sellers and Volume pages should fill with
   sample data.

## Part C. Tighten the Space's setting

On the Space: **Settings → Variables and secrets**, change `MUHR_CORS_ALLOW_ORIGINS` from `*` to your
Vercel address exactly as shown, for example `https://muhr.vercel.app` (no `/` at the end). To allow
several addresses, separate them with commas. The Space restarts when a variable changes, so wait for
**Running** again (about 2 to 3 minutes) and reload the dashboard.

Vercel's preview links each have their own address. If you use them, keep `*`. The API has no logins
or cookies, so `*` is acceptable for a demo: it only means any website's page may call it.

## Final check

Open the Vercel address and add `/?pitch=1`. Press **Hire a seller**, run a preset, and watch the eight
stages light up. Open the job's receipt: **Verify** should show a green seal.

## If something is wrong

| What you see | What to do |
| --- | --- |
| The Space shows a red error in **Logs** | Copy the error text. Pressing **Restart** on the Space often clears a one-off failure. |
| `/health` keeps showing "starting" for more than 5 minutes | Read **Logs**; it says which step it is on (downloading, installing, starting). |
| The dashboard loads but shows no data, or its header says "Registry offline" | Check `VITE_API_BASE_URL` on Vercel (right address, no `/` at the end), then **Redeploy**. Then check Part C: the CORS value must match the Vercel address exactly, or be `*`. |
| Jobs fail with a "rate-limited" or "rejected" message | Run `python scripts/check_llm.py` to see which keys work. Rejected keys (401/403) are dropped until the Space restarts. |
| The Space is asleep | Open its address and wait about a minute. |

## What to expect from the free plans

- **Sleeping.** A Space with no visitors for a couple of days goes to sleep; the next visit wakes it in
  about a minute. Open it, and run one job, a few minutes before a demo.
- **Data resets.** The disk is not permanent, so the database is recreated when the Space restarts,
  with the built-in sample data. Jobs from earlier sessions are gone.
- **No per-job containers.** Docker is not available inside a Space, so the optional isolated worker
  (`MUHR_SELLER_ISOLATION=docker`) is off. Jobs run in-process.
- **Public repository.** `app.py` downloads the code from GitHub, so the repository must be public.
- **Slow restarts.** Every start downloads the code and installs packages again (about two minutes).
- **Real Lightning payments** are not part of this setup. See [`WALLET_FUNDING.md`](WALLET_FUNDING.md).

## How it works

`app.py` serves the Space's one public port. It forwards `/api/*` and `/health` to the real backend and
shows a status page everywhere else. In the background it downloads this repository, installs the
pinned requirements into its own virtual environment, and runs `scripts/run_space.py` on an internal
port. That script starts the three sellers and the registry, and exits if any of them stops, and
`app.py` then restarts it. With several keys in `LLM_API_KEYS`, each job starts on the next key; a key
that is rate-limited (HTTP 429) rests for a while, a timeout or server error moves on to the next key,
and a key the provider rejects is dropped until the Space restarts. The older single `GROQ_API_KEY` and
`GEMINI_API_KEY` secrets still work and are tried after the list. The admin key and seller keys are
generated on every start; set `MUHR_ADMIN_KEY` and `MUHR_SELLER_KEY_SEL_SUMMARIZER`, `_SEL_CLASSIFIER`,
`_SEL_URDU` as secrets only if you want fixed values. To run a fork or another branch, set the variables
`MUHR_REPO_URL` and `MUHR_REPO_REF`. A Dockerfile for accounts that do have Docker Spaces is in
[`deploy/huggingface-docker/`](../deploy/huggingface-docker/).
