# Auteur : Gilles - Projet : AGC Space
# Configuration Gunicorn pour Render.com
# Render > Settings > Start Command :
#   gunicorn -c deploy/gunicorn_render.conf.py agc_core.wsgi:application

import multiprocessing
import os

# ── Workers ───────────────────────────────────────────────────────────────────
# Render Free/Starter : 1 CPU → 3 workers
# Render Standard     : 2 CPU → 5 workers
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))  # 120s — Render health check
keepalive = 5

# ── Binding ───────────────────────────────────────────────────────────────────
# Render expose le port via la variable PORT (défaut 10000)
port = os.getenv('PORT', '10000')
bind = f'0.0.0.0:{port}'

# ── Logs — stdout uniquement sur Render (pas de fichiers) ────────────────────
accesslog  = '-'   # stdout
errorlog   = '-'   # stderr
loglevel   = os.getenv('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sms'

# ── Process ───────────────────────────────────────────────────────────────────
proc_name = 'agcspace'
daemon    = False  # Render gère le process lui-même
