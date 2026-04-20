# Auteur : Gilles — Projet : AGC Space
# Script PowerShell — Mode tunnel Ngrok (port unique)
#
# Usage :
#   .\scripts\tunnel.ps1           → Lance backend + frontend
#   .\scripts\tunnel.ps1 -Build    → Build Next.js avant de lancer
#   .\scripts\tunnel.ps1 -Prod     → Mode production (Gunicorn + Next.js standalone)

param(
    [switch]$Build,
    [switch]$Prod,
    [int]$DjangoPort = 8000,
    [int]$NextPort = 3000
)

$ErrorActionPreference = "Stop"

# ── Couleurs ──────────────────────────────────────────────────────────────────
function Write-Cyan($msg)   { Write-Host $msg -ForegroundColor Cyan }
function Write-Green($msg)  { Write-Host $msg -ForegroundColor Green }
function Write-Yellow($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Red($msg)    { Write-Host $msg -ForegroundColor Red }

# ── Nettoyage à l'arrêt ───────────────────────────────────────────────────────
$jobs = @()
function Cleanup {
    Write-Yellow "`n▶ Arrêt des processus..."
    $jobs | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Write-Green "✓ Arrêt propre"
    exit 0
}
Register-EngineEvent PowerShell.Exiting -Action { Cleanup }

# ── Header ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Cyan "╔══════════════════════════════════════════╗"
Write-Cyan "║     AGC Space — Mode Tunnel Ngrok        ║"
Write-Cyan "╚══════════════════════════════════════════╝"
Write-Host ""

# ── Build optionnel ───────────────────────────────────────────────────────────
if ($Build -or $Prod) {
    Write-Cyan "▶ [1/3] Build Next.js standalone..."
    Push-Location frontend
    npm run build
    Pop-Location
    Write-Green "  ✓ Build terminé"
}

# ── Lancement Next.js ─────────────────────────────────────────────────────────
if ($Prod) {
    Write-Cyan "▶ Lancement Next.js standalone sur :$NextPort..."
    $env:PORT = $NextPort
    $nextJob = Start-Process -FilePath "node" -ArgumentList "frontend\.next\standalone\server.js" -PassThru -NoNewWindow
    $jobs += $nextJob.Id
} else {
    Write-Cyan "▶ Lancement Next.js dev sur :$NextPort..."
    $nextJob = Start-Process -FilePath "npm" -ArgumentList "run", "dev", "--", "--port", $NextPort -WorkingDirectory "frontend" -PassThru -NoNewWindow
    $jobs += $nextJob.Id
}

# Attendre que Next.js soit prêt
Write-Cyan "▶ Attente démarrage Next.js..."
$ready = $false
for ($i = 1; $i -le 15; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$NextPort" -TimeoutSec 1 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 404) {
            Write-Green "  ✓ Next.js prêt sur :$NextPort"
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
        Write-Host "." -NoNewline
    }
}
Write-Host ""

if (-not $ready) {
    Write-Red "✗ Next.js n'a pas démarré dans les temps"
    Cleanup
}

# ── Lancement Django ──────────────────────────────────────────────────────────
Write-Cyan "▶ Lancement Django sur :$DjangoPort (proxy catch-all actif)..."
Write-Host ""
Write-Green "╔══════════════════════════════════════════╗"
Write-Green "║  ✓ Application prête !                   ║"
Write-Green "║                                          ║"
Write-Green "║  Local  → http://localhost:$DjangoPort         ║"
Write-Green "║  Ngrok  → ngrok http $DjangoPort               ║"
Write-Green "║                                          ║"
Write-Green "║  API    → /api/v1/                       ║"
Write-Green "║  Admin  → /admin/                        ║"
Write-Green "║  App    → / (proxifié vers Next.js)      ║"
Write-Green "╚══════════════════════════════════════════╝"
Write-Host ""

if ($Prod) {
    & gunicorn -c deploy/gunicorn.conf.py agc_core.wsgi:application
} else {
    & python manage.py runserver $DjangoPort
}
