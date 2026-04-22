#!/usr/bin/env bash
# Auteur : Gilles - Projet : AGC Space
# Script de build exécuté par Render avant le démarrage du service
# Render > Settings > Build Command : ./deploy/render_build.sh

set -o errexit  # Arrêt immédiat si une commande échoue

echo "==> Installation des dépendances..."
pip install -r requirements.txt

echo "==> Application des migrations..."
python manage.py migrate --noinput

echo "==> Collecte des fichiers statiques (WhiteNoise)..."
python manage.py collectstatic --noinput --clear

echo "==> Build terminé."
