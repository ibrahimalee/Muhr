# Copies MDK Agent Wallet data from your user profile into repo-local secrets/ (gitignored).
# Run from repo root:  powershell -ExecutionPolicy Bypass -File scripts/backup_mdk_wallet.ps1
# Requires: MDK initialized (folder $env:USERPROFILE\.mdk-wallet exists).

$ErrorActionPreference = "Stop"
$src = Join-Path $env:USERPROFILE ".mdk-wallet"
# scripts/ -> repo root
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dest = Join-Path $repoRoot "secrets\mdk-wallet-backup"

if (-not (Test-Path $src)) {
    Write-Error "MDK wallet not found at: $src`nRun: npx -y @moneydevkit/agent-wallet@0.22.0 init"
}

New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
if (Test-Path $dest) {
    Remove-Item -Recurse -Force $dest
}
Copy-Item -Path $src -Destination $dest -Recurse -Force

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$note = Join-Path $dest "BACKUP_NOTE.txt"
@"
MDK wallet copy (auto). Do not commit this folder; secrets/ is gitignored.
Source: $src
Copied: $stamp
Keep a second copy offline (password manager or encrypted drive). The mnemonic in config is your funds.
"@ | Set-Content -Path $note -Encoding UTF8

Write-Host "Backed up to: $dest"
Get-ChildItem $dest | Format-Table Name, Length, LastWriteTime
