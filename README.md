# keen-py

```
    __ __
   / //_/__  ___  ____
  / ,< / _ \/ _ \/ __ \
 / /| /  __/  __/ / / /
/_/ |_\___/\___/_/ /_/

```

Keen, as in keen observation, is a reconnaissance and OSINT framework for ethical hacking and penetration testing. It runs as an interactive Metasploit-style shell and, optionally, as a FastAPI web server backing a single-page graph UI. Module results are ingested into per-case SQLite graph databases (`.keen` files) as STIX 2.1 / MISP-annotated nodes and edges, and can be auto-chained via the built-in *magic* engine.

> **Ethical use only.** Keen is intended for authorized security testing, research,
> and educational use. You are responsible for complying with all applicable laws
> and for having permission to investigate any target.

## Requirements

- Python 3.11+
- Git (to fetch the vendored [Sherlock](https://github.com/sherlock-project/sherlock) submodule)

## Installation

```bash
git clone --recurse-submodules https://github.com/sammwyy/keen-py.git
cd keen-py

# Recommended: install the package (and its dependencies) into a virtualenv.
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .

# For development (tests, linting, type-checking, stubs):
pip install -e ".[dev]"
```

If you cloned without `--recurse-submodules`, fetch Sherlock afterwards:

```bash
git submodule update --init --recursive
```

> Dependencies are declared in `pyproject.toml`. `keen.py` also ships a convenience
> auto-installer that pip-installs anything missing on first launch; set
> `KEEN_SKIP_DEP_CHECK=1` to disable it once the package is installed.

## Usage

After `pip install -e .` a `keen` command is available (equivalently, run `python keen.py`):

```bash
keen                       # interactive shell
keen --debug               # verbose logging
keen --check-deps          # force dependency verification/install

# Web server (FastAPI + uvicorn, serves the SPA in web/ plus REST + WebSocket):
keen --web --host 127.0.0.1 --port 8000
```

Inside the shell:

```
keen> use discovery/whois
keen> set TARGET example.com
keen> run
keen> magic example.com          # auto-detect type and chain relevant modules
keen> workspace create my-case   # investigations are saved to cases/my-case.keen
```

### Docker

```bash
docker build -t keen .
docker run --rm -p 8000:8000 -v "$PWD/cases:/app/cases" keen   # web UI on :8000
```

## Development

```bash
pip install -e ".[dev]"

pytest                 # run the test suite (tests/)
pytest --cov           # with coverage
ruff check . && ruff format --check .   # lint & format
pyrefly check          # type-check
pre-commit install     # enable git hooks (ruff + hygiene)
```

## Module categories

| Category      | Modules                                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------- |
| `analysis`    | Hudson Rock (infostealer exposure), Leak Check (breach lookups: LeakCheck, DeHashed, HIBP, BreachVIP)         |
| `discovery`   | WHOIS, DNS Enum, Historical DNS, Subdomain Enum                                                               |
| `enumeration` | Domain/Email Enrichment, Email Verification, Email Finder, GitHub, Phone Verification, Sherlock, User Scanner |
| `web`         | WAF/CDN Detection                                                                                             |
| `helpers`     | Email→Username, Org→Domain, URL→Domain                                                                        |
| `intel`       | *(planned — Shodan, Censys, GreyNoise, reputation feeds)*                                                     |

## License

Distributed under the GNU GPL v3. See [`LICENSE`](LICENSE).
