#!/usr/bin/env bash
# Auteur : Gilles — Projet : AGC Space
# Script de lancement mode tunnel Ngrok (port unique)
#
# Usage :
#   ./scripts/tunnel.sh           → Lance backend + frontend + instructions Ngrok
#   ./scripts/tunnel.sh --build   → Build Next.js avant de lancer
#   ./scripts/tunnel.sh --prod    → Mode production (Gunicorn + Next.js standalone)
#
# Architecture :
#   Ngrok → :8000 (Django) → proxy catch-all → :3000 (Next.js, interne)

set -e

# ── Couleurs ──────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

DJANGO_PORT=${DJANGO_PORT:-8000}
NEXT_PORT=${NEXT_PORT:-3000}
FRONTEND_DIR="frontend"
BUILD_MODE=false
PROD_MODE=false

# ── Arguments ─────────────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --build) BUILD_MODE=true ;;
    --prod)  PROD_MODE=true; BUILD_MODE=true ;;
  esac
done

# ── Nettoyage à l'arrêt (Ctrl+C) ─────────────────────────────────────────────
cleanup() {
  echo ""
  echo -e "${YELLOW}▶ Arrêt des processus...${RESET}"
  kill $(jobs -p) 2>/dev/null || true
  echo -e "${GREEN}✓ Arrêt propre${RESET}"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}║     AGC Space — Mode Tunnel Ngrok        ║${RESET}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Build optionnel ───────────────────────────────────────────────────────────
if [ "$BUILD_MODE" = true ]; then
  echo -e "${CYAN}▶ [1/3] Build Next.js standalone...${RESET}"
  cd "$FRONTEND_DIR"
  npm run build
  cd ..
  echo -e "${GREEN}  ✓ Build terminé${RESET}"
fi

# ── Lancement Next.js ─────────────────────────────────────────────────────────
if [ "$PROD_MODE" = true ]; then
  echo -e "${CYAN}▶ Lancement Next.js standalone sur :${NEXT_PORT}...${RESET}"
  PORT=$NEXT_PORT node "$FRONTEND_DIR/.next/standalone/server.js" &
  NEXT_PID=$!
else
  echo -e "${CYAN}▶ Lancement Next.js dev sur :${NEXT_PORT}...${RESET}"
  cd "$FRONTEND_DIR" && npm run dev -- --port "$NEXT_PORT" &
  NEXT_PID=$!
  cd ..
fi

# Attendre que Next.js soit prêt
echo -e "${CYAN}▶ Attente démarrage Next.js...${RESET}"
for i in $(seq 1 15); do
  if curl -s "http://127.0.0.1:${NEXT_PORT}" > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Next.js prêt sur :${NEXT_PORT}${RESET}"
    break
  fi
  sleep 1
  echo -n "."
done
echo ""

# ── Lancement Django ──────────────────────────────────────────────────────────
echo -e "${CYAN}▶ Lancement Django sur :${DJANGO_PORT} (proxy catch-all actif)...${RESET}"
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}║  ✓ Application prête !                   ║${RESET}"
echo -e "${GREEN}║                                          ║${RESET}"
echo -e "${GREEN}║  Local  → http://localhost:${DJANGO_PORT}         ║${RESET}"
echo -e "${GREEN}║  Ngrok  → ngrok http ${DJANGO_PORT}               ║${RESET}"
echo -e "${GREEN}║                                          ║${RESET}"
echo -e "${GREEN}║  API    → /api/v1/                       ║${RESET}"
echo -e "${GREEN}║  Admin  → /admin/                        ║${RESET}"
echo -e "${GREEN}║  App    → / (proxifié vers Next.js)      ║${RESET}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""

if [ "$PROD_MODE" = true ]; then
  gunicorn -c deploy/gunicorn.conf.py agc_core.wsgi:application
else
  python manage.py runserver "$DJANGO_PORT"
fi
