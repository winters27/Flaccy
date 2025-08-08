# gunicorn.conf.py
bind = "0.0.0.0:5000"
workers = 1
threads = 4
worker_class = "gevent"
timeout = 60
keepalive = 5
preload_app = False
