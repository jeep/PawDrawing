#!/bin/bash
# Multiple workers require a shared session store (FileSystemCache).
# Do NOT switch to an in-memory store (e.g. SimpleCache) without using
# a single worker or migrating to Redis.
gunicorn --bind=0.0.0.0:8000 --timeout=120 --workers=2 run:app
