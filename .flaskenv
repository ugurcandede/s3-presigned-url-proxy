# Local dev port. 8087 mirrors the Docker host mapping (8087:8088) and keeps the
# proxy off port 8088 so it won't collide with another app (e.g. a UI) running there.
FLASK_APP=app.py
FLASK_RUN_HOST=0.0.0.0
FLASK_RUN_PORT=8087
