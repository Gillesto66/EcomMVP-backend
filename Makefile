# ============================================================================
# Auteur : Gilles — Projet : AGC Space
# Makefile — Automatisation du workflow développement + tunnel Ngrok
#
# Commandes principales :
#   make dev          → Lance backend + frontend en parallèle (mode dev normal)
#   make tunnel       → Lance backend + frontend + affiche l'URL Ngrok
#   make build        → Build Next.js et copie vers staticfiles/
#   make prod         → Build + lance uniquement Django (mode production)
# ============================================================================

# ── Variables ─────────────────────────────────────────────────────────────────
PYTHON      := python
PIP         := pip
NPM         := npm
DJANGO      := $(PYTHON) manage.py
FRONTEND    := frontend
STATIC_DIR  := staticfiles
NEXT_OUT    := $(FRONTEND)/.next/standalone

# Port Django (modifiable via env)
DJANGO_PORT ?= 8000
NEXT_PORT   ?= 3000

# Couleurs terminal
CYAN  := \033[0;36m
GREEN := \033[0;32m
YELLOW:= \033[0;33m
RED   := \033[0;31m
RESET := \033[0m

.PHONY: help dev dev-back dev-front tunnel build prod install migrate clean logs

# ── Aide ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "$(CYAN)╔══════════════════════════════════════════╗$(RESET)"
	@echo "$(CYAN)║         AGC Space — Makefile             ║$(RESET)"
	@echo "$(CYAN)╚══════════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "$(GREEN)Développement :$(RESET)"
	@echo "  make dev          Lance backend (8000) + frontend (3000)"
	@echo "  make dev-back     Lance uniquement Django"
	@echo "  make dev-front    Lance uniquement Next.js"
	@echo ""
	@echo "$(GREEN)Tunnel Ngrok (port unique) :$(RESET)"
	@echo "  make tunnel       Lance tout + ouvre le tunnel sur :$(DJANGO_PORT)"
	@echo ""
	@echo "$(GREEN)Build & Production :$(RESET)"
	@echo "  make build        Build Next.js standalone"
	@echo "  make prod         Build + lance Django seul (proxy intégré)"
	@echo ""
	@echo "$(GREEN)Utilitaires :$(RESET)"
	@echo "  make install      Installe toutes les dépendances"
	@echo "  make migrate      Applique les migrations Django"
	@echo "  make clean        Supprime les fichiers générés"
	@echo "  make logs         Affiche les logs Django en temps réel"
	@echo ""

# ── Installation ──────────────────────────────────────────────────────────────
install:
	@echo "$(CYAN)▶ Installation des dépendances Python...$(RESET)"
	$(PIP) install -r requirements.txt
	@echo "$(CYAN)▶ Installation des dépendances Node.js...$(RESET)"
	cd $(FRONTEND) && $(NPM) install
	@echo "$(GREEN)✓ Dépendances installées$(RESET)"

# ── Migrations ────────────────────────────────────────────────────────────────
migrate:
	@echo "$(CYAN)▶ Application des migrations...$(RESET)"
	$(DJANGO) migrate
	@echo "$(GREEN)✓ Migrations appliquées$(RESET)"

# ── Développement normal (2 ports) ────────────────────────────────────────────
dev-back:
	@echo "$(CYAN)▶ Démarrage Django sur :$(DJANGO_PORT)...$(RESET)"
	set PYTHONIOENCODING=utf-8 && $(DJANGO) runserver $(DJANGO_PORT)

dev-front:
	@echo "$(CYAN)▶ Démarrage Next.js sur :$(NEXT_PORT)...$(RESET)"
	cd $(FRONTEND) && $(NPM) run dev -- --port $(NEXT_PORT)

# Lance les deux en parallèle (nécessite un terminal qui supporte &)
dev:
	@echo "$(CYAN)▶ Lancement en mode développement (2 ports)...$(RESET)"
	@echo "$(YELLOW)  Backend  → http://localhost:$(DJANGO_PORT)$(RESET)"
	@echo "$(YELLOW)  Frontend → http://localhost:$(NEXT_PORT)$(RESET)"
	@echo "$(YELLOW)  Ctrl+C pour arrêter les deux$(RESET)"
	@$(MAKE) dev-back & $(MAKE) dev-front; wait

# ── Mode tunnel Ngrok (port unique :8000) ─────────────────────────────────────
# Django proxifie tout vers Next.js en interne
tunnel:
	@echo "$(CYAN)╔══════════════════════════════════════════╗$(RESET)"
	@echo "$(CYAN)║     Mode Tunnel Ngrok — Port unique      ║$(RESET)"
	@echo "$(CYAN)╚══════════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "$(YELLOW)Architecture :$(RESET)"
	@echo "  Ngrok → :$(DJANGO_PORT) (Django) → proxy → :$(NEXT_PORT) (Next.js interne)"
	@echo ""
	@echo "$(CYAN)▶ Démarrage Next.js en arrière-plan sur :$(NEXT_PORT)...$(RESET)"
	@cd $(FRONTEND) && $(NPM) run dev -- --port $(NEXT_PORT) &
	@echo "$(CYAN)▶ Attente démarrage Next.js (5s)...$(RESET)"
	@sleep 5
	@echo "$(CYAN)▶ Démarrage Django sur :$(DJANGO_PORT) (avec proxy catch-all)...$(RESET)"
	@echo ""
	@echo "$(GREEN)✓ Lancez maintenant dans un autre terminal :$(RESET)"
	@echo "$(GREEN)  ngrok http $(DJANGO_PORT)$(RESET)"
	@echo ""
	set PYTHONIOENCODING=utf-8 && $(DJANGO) runserver $(DJANGO_PORT)

# ── Build Next.js → Django staticfiles ───────────────────────────────────────
build:
	@echo "$(CYAN)╔══════════════════════════════════════════╗$(RESET)"
	@echo "$(CYAN)║         Build Next.js Standalone         ║$(RESET)"
	@echo "$(CYAN)╚══════════════════════════════════════════╝$(RESET)"
	@echo ""

	@echo "$(CYAN)▶ [1/4] Nettoyage des anciens fichiers...$(RESET)"
	@if exist "$(FRONTEND)\.next" rmdir /s /q "$(FRONTEND)\.next" 2>nul || true
	@echo "$(GREEN)  ✓ Nettoyage terminé$(RESET)"

	@echo "$(CYAN)▶ [2/4] Build Next.js (mode standalone)...$(RESET)"
	cd $(FRONTEND) && $(NPM) run build
	@echo "$(GREEN)  ✓ Build terminé$(RESET)"

	@echo "$(CYAN)▶ [3/4] Collecte des fichiers statiques Django...$(RESET)"
	$(DJANGO) collectstatic --noinput --clear
	@echo "$(GREEN)  ✓ Collecte terminée$(RESET)"

	@echo ""
	@echo "$(GREEN)╔══════════════════════════════════════════╗$(RESET)"
	@echo "$(GREEN)║  ✓ Build terminé avec succès !           ║$(RESET)"
	@echo "$(GREEN)║                                          ║$(RESET)"
	@echo "$(GREEN)║  Next.js standalone : frontend/.next/    ║$(RESET)"
	@echo "$(GREEN)║  Lancez : make prod                      ║$(RESET)"
	@echo "$(GREEN)╚══════════════════════════════════════════╝$(RESET)"

# ── Production : build + lancement ───────────────────────────────────────────
prod: build
	@echo "$(CYAN)▶ Lancement en mode production...$(RESET)"
	@echo "$(YELLOW)  Démarrage Next.js standalone en arrière-plan...$(RESET)"
	@node $(FRONTEND)/.next/standalone/server.js &
	@echo "$(CYAN)▶ Attente démarrage Next.js (3s)...$(RESET)"
	@sleep 3
	@echo "$(YELLOW)  Démarrage Gunicorn...$(RESET)"
	gunicorn -c deploy/gunicorn.conf.py agc_core.wsgi:application

# ── Nettoyage ─────────────────────────────────────────────────────────────────
clean:
	@echo "$(CYAN)▶ Nettoyage des fichiers générés...$(RESET)"
	@if exist "$(FRONTEND)\.next" rmdir /s /q "$(FRONTEND)\.next" 2>nul || true
	@if exist "$(STATIC_DIR)" rmdir /s /q "$(STATIC_DIR)" 2>nul || true
	@if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul || true
	@echo "$(GREEN)✓ Nettoyage terminé$(RESET)"

# ── Logs ──────────────────────────────────────────────────────────────────────
logs:
	@echo "$(CYAN)▶ Logs Django en temps réel (Ctrl+C pour arrêter)...$(RESET)"
	@tail -f logs/agcspace.log 2>nul || Get-Content logs/agcspace.log -Wait
