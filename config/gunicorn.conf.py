"""
Gunicorn Production Server Configuration for GramSetu

Reference configuration for deploying the Django WSGI application on Linux hosts.
Usage:
    gunicorn -c config/gunicorn.conf.py config.wsgi:application
"""

import multiprocessing
import os

# ------------------------------------------------------------------------------
# Network Socket & Binding
# ------------------------------------------------------------------------------
# Binds strictly to loopback interface. In production, Nginx reverse proxy terminates
# external traffic and proxies to this internal port or a Unix domain socket.
# NEVER bind to '0.0.0.0' or expose this port directly to public networks.
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")
backlog = 2048

# ------------------------------------------------------------------------------
# Worker Processes & Concurrency
# ------------------------------------------------------------------------------
# Standard recommendation: (2 * CPUs) + 1. Capped at 4 for typical 1-2 vCPU Panchayat VMs.
cpu_count = multiprocessing.cpu_count()
workers = int(os.getenv("GUNICORN_WORKERS", min(4, max(2, cpu_count * 2 + 1))))
worker_class = "sync"
threads = 1
worker_connections = 1000

# Timeout: 60s accommodates large official document uploads (up to 50 MB ceiling)
timeout = int(os.getenv("GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
keepalive = 5

# Periodic worker recycling to prevent memory leaks in long-running processes
max_requests = 1000
max_requests_jitter = 50

# ------------------------------------------------------------------------------
# Security & Process Identity
# ------------------------------------------------------------------------------
# In production systemd execution, user and group are managed by the service unit.
# When running standalone on Linux, unprivileged user should be specified:
# user = "gramsetu"
# group = "gramsetu"

# Limits on HTTP request line and headers to prevent buffer overflow / slowloris attacks
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # stdout for systemd journal
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")    # stderr for systemd journal
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)ss'

# ------------------------------------------------------------------------------
# Process Naming
# ------------------------------------------------------------------------------
proc_name = "gramsetu_wsgi"
