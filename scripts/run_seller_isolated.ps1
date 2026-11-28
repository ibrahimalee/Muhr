# Run a MUHR seller whose *job processing* happens in a network-less container.
#
# The HTTP seller (which must talk to the registry and buyers) runs on the host.
# For every job it starts `docker run --network none --read-only --cap-drop ALL ...
# python -m sellers.worker`; the worker opens the sealed input, runs the offline
# pipeline and returns only the encrypted result. The host process never sees
# plaintext, and the code that does see it has no network to leak it through.
#
# Usage:
#   ./scripts/run_seller_isolated.ps1 -Capability summarizer
#   ./scripts/run_seller_isolated.ps1 -Capability classifier -Port 8002 -DryRun

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('summarizer', 'classifier')]
    [string] $Capability,

    [int] $Port = 0,

    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
if ($Port -eq 0) { $Port = if ($Capability -eq 'summarizer') { 8001 } else { 8002 } }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker not on PATH. Install Docker Desktop and re-run."
    exit 1
}

$repoRoot = Resolve-Path -LiteralPath "$PSScriptRoot/.."
Set-Location $repoRoot
$image = "muhr/seller-$($Capability):latest"

if ($DryRun) {
    Write-Host "[muhr] dry-run: would build $image and start sellers.$Capability.app on :$Port with MUHR_SELLER_ISOLATION=docker"
    exit 0
}

Write-Host "[muhr] building worker image $image" -ForegroundColor Cyan
docker build -q -t $image -f "sellers/$Capability/Dockerfile" . | Out-Null
if (-not $?) { exit 1 }
$imageId = docker image inspect $image --format '{{.Id}}'

$env:MUHR_SELLER_ISOLATION = 'docker'
$env:MUHR_SELLER_WORKER_IMAGE = $image
$env:MUHR_SELLER_IMAGE_HASH = $imageId
if (-not $env:MUHR_SELLER_X25519_PRIVATE_B64) {
    $env:MUHR_SELLER_X25519_PRIVATE_B64 = python -c "from shared.crypto_utils import generate_x25519_keypair,b64e; print(b64e(generate_x25519_keypair()[0]))"
}

Write-Host "[muhr] seller $Capability on :$Port; jobs run in $image with --network none ($imageId)" -ForegroundColor Cyan
python -m uvicorn "sellers.$Capability.app:app" --host 127.0.0.1 --port $Port
