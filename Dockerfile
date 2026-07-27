# syntax=docker/dockerfile:1

# base python image for custom image
FROM python:3.12-trixie

ENV OSINT_HOME=/data \
    PIP_NO_CACHE_DIR=1

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
RUN pip install --no-cache-dir ".[app]" gunicorn
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
CMD ["gunicorn", "--preload", "--workers=4", "--bind=0.0.0.0:8002", "sphinxcontrib.osint.run:app"]
