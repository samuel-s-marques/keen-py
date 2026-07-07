# Keen — container image. Builds the package and runs the web server by default.
#   docker build -t keen .
#   docker run --rm -p 8000:8000 -v "$PWD/cases:/app/cases" keen
FROM python:3.11-slim

# The interactive shell and modules shell out to a few tools; git is needed if
# the sherlock submodule is fetched at build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (better layer caching), then the package itself.
COPY pyproject.toml README.md LICENSE ./
COPY keen.py ./
COPY src ./src

ENV KEEN_SKIP_DEP_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install -e .

# App assets and vendored tools (web SPA, sherlock submodule if present).
COPY web ./web
COPY vendors ./vendors

EXPOSE 8000

# Serve the web UI/API by default; override to drop into the interactive shell.
ENTRYPOINT ["keen"]
CMD ["--web", "--host", "0.0.0.0", "--port", "8000"]
