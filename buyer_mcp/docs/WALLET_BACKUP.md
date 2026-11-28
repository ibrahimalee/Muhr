# MDK wallet backup (do not commit secrets)

Your **live** MDK files live in your user profile:

- **Windows:** `%USERPROFILE%\.mdk-wallet\` (typically `C:\Users\<you>\.mdk-wallet\`)
- **Config:** `config.json` (contains mnemonic — treat as highly sensitive)
- **Daemon / logs:** same folder

## Copy into this repo (gitignored)

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup_mdk_wallet.ps1
```

That copies `~/.mdk-wallet` → **`secrets/mdk-wallet-backup/`** (the whole `secrets/` tree is listed in `.gitignore` so it is not committed).

Re-run the script anytime you want a fresh snapshot (it replaces the previous `mdk-wallet-backup` folder).

## Best practice

- Also store the **mnemonic** in a password manager or offline backup (the folder copy is not a substitute for a clean mnemonic backup).
- Never `git add secrets/` or paste `config.json` into issues/PRs.
