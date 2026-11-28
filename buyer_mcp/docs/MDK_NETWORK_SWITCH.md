# Switching MDK: mainnet ↔ Signet (this machine)

Your **mainnet** wallet (the one used for the team invoice) was **preserved** when Signet was enabled. Nothing was deleted.

## Where things live

| Location | Contents |
|----------|----------|
| `%USERPROFILE%\.mdk-wallet` | **Active** wallet (currently **Signet** after setup) |
| `%USERPROFILE%\.mdk-wallet.mainnet-keep` | **Mainnet** files (invoice / future mainnet funds use this when restored) |
| `secrets/mdk-mainnet-preserve-<timestamp>/` | Extra copy of mainnet at time of switch (gitignored) |

`secrets/` is never committed; it is a safety copy only.

## When mainnet payment arrives: use mainnet again

1. `npx -y @moneydevkit/agent-wallet@0.22.0 stop`
2. Rename **active** signet data out of the way:  
   `%USERPROFILE%\.mdk-wallet` → `%USERPROFILE%\.mdk-wallet.signet-keep` (keeps your signet wallet if you want it later)
3. Rename the mainnet backup into place:  
   `%USERPROFILE%\.mdk-wallet.mainnet-keep` → `%USERPROFILE%\.mdk-wallet`
4. `npx -y @moneydevkit/agent-wallet@0.22.0 start`
5. `npx -y @moneydevkit/agent-wallet@0.22.0 balance`

Muhr + Buyer MCP (`DEMO_MODE=false`) will then talk to **mainnet** MDK again.

## Go back to Signet later

Reverse: stop, rename `.mdk-wallet` → `.mdk-wallet.signet-keep`, rename `.mdk-wallet.mainnet-keep` back from wherever you left it, start.

## If the profile folder is missing

Use the **mnemonic** you saved for mainnet to recover (or restore from `secrets/mdk-mainnet-preserve-*/config.json` on this PC only—do not commit).
