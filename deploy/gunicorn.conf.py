# Auteur : Gilles - Projet : AGC Space - Module : Déploiement Gunicorn
"""
Configuration Gunicorn pour la production.
Lancement : gunicorn -c deploy/gunicorn.conf.py agc_core.wsgi:application
"""
import multiprocessing
import os

# ── Workers ───────────────────────────────────────────────────────────────────
# Règle : (2 × CPU) + 1
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 5

# ── Binding ───────────────────────────────────────────────────────────────────
bind = os.getenv('GUNICORN_BIND', '127.0.0.1:8000')

# ── Logs ──────────────────────────────────────────────────────────────────────
accesslog = os.getenv('GUNICORN_ACCESS_LOG', '/var/log/agcspace/gunicorn_access.log')
errorlog = os.getenv('GUNICORN_ERROR_LOG', '/var/log/agcspace/gunicorn_error.log')
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# ── Process ───────────────────────────────────────────────────────────────────
proc_name = 'agcspace'
pidfile = '/tmp/agcspace.pid'
daemon = False  # Géré par systemd

# ── Sécurité ──────────────────────────────────────────────────────────────────
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
