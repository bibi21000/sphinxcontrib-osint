# syntax=docker/dockerfile:1

# base python image for custom image
FROM python:3.14-trixie

ENV OSINT_HOME=/data \
    PIP_NO_CACHE_DIR=1 \
    GUNICORN_TIMEOUT=120 \
    GUNICORN_WORKER_CLASS=gthread \
    GUNICORN_WORKERS=4 \
    GUNICORN_THREADS=4

WORKDIR /app

# copy only what's needed to resolve/install deps first (better layer caching:
# this layer only rebuilds when these files change, not on every source edit)
COPY pyproject.toml /app/
COPY sphinxcontrib /app/sphinxcontrib/
COPY docker/Makefile.xapian /app/
COPY docker/Makefile /app/

# single RUN: combine the apt deps (if you actually need python3-sphinx/python3-dev,
# uncomment), pip installs (merged into one resolver call to avoid reinstall churn),
# xapian build, and gunicorn — fewer layers, smaller final image, faster build cache
RUN pip install --no-cache-dir ".[app]" gunicorn redis
RUN make xapian; \
    rm -rf xapian/xapian_packages; \
    rm -rf xapian/xapian_build; \
    mkdir -p /data

# create a non-root user and hand over ownership of app + data dirs
#RUN groupadd -r osint && useradd -r -g osint -d /data osint \
#    && chown -R osint:osint /app /data
#USER osint

EXPOSE 8002

VOLUME ["/data"]

# run the flask server
# gthread (rather than the sync default) lets one worker serve several
# requests at once via real OS threads, so one slow /chat/... call (open-webui
# taking its time to answer) only blocks the thread handling it, instead of
# freezing the whole worker process until GUNICORN_TIMEOUT kills it - see
# GUNICORN_TIMEOUT above, which stays comfortably above the app's own
# osint_webui_chat_read_timeout so that a slow chat backend surfaces as a
# clean 502 from Flask rather than a gunicorn SIGKILL mid-request.
CMD ["sh", "-c", "gunicorn --preload --workers=${GUNICORN_WORKERS} --worker-class=${GUNICORN_WORKER_CLASS} --threads=${GUNICORN_THREADS} --timeout ${GUNICORN_TIMEOUT} --bind=0.0.0.0:8002 sphinxcontrib.osint.run:app"]
