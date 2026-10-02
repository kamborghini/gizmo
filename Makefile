# The developer's entry points. Every command a person runs against this repo
# is here, so nothing lives only in somebody's memory.
#
#   make install        create .venv (Python 3.14) from the hashed locks
#   make run            start the app on :8000, loading .env if there is one
#   make test           the dispatch suite (about a minute, no network)
#   make test-frontend  the static guards on the single-page app (seconds)
#   make test-forecast  the forecast package (skips itself without pandas)
#   make sast           CI's blocking security scan (bandit, high severity)
#   make check          everything CI runs that needs no network
#   make env-doc        regenerate docs/ENVIRONMENT.md from the code
#   make lock           compile the exact pins (*.in) into the hashed lock files

PY ?= .venv/bin/python

.PHONY: help install run test test-frontend test-forecast sweep sast env-doc check lock

help:
	@sed -n '4,13p' Makefile

# requirements.in and forecast/requirements-service.in hold the direct pins;
# the .txt beside each is every package installed, transitive ones included,
# pinned with hashes, for every platform (macOS here, Linux in the image and
# CI). The header names the pip-compile command Dependabot regenerates them
# with when it raises a pin. Needs uv (brew install uv).
LOCK = uv pip compile --universal --python-version 3.14 --generate-hashes --quiet
lock:
	$(LOCK) requirements.in -o requirements.txt \
	  --custom-compile-command "pip-compile --generate-hashes --output-file=requirements.txt requirements.in"
	cd forecast && $(LOCK) requirements-service.in -o requirements-service.txt \
	  --custom-compile-command "pip-compile --generate-hashes --output-file=requirements-service.txt requirements-service.in"
	cd forecast && $(LOCK) requirements-m5.in -o requirements-m5.txt \
	  --custom-compile-command "pip-compile --generate-hashes --output-file=requirements-m5.txt requirements-m5.in"

# The same Python as the images and CI, from the same hashed lock. The forecast
# lock and the scanners make check uses come too, so `make check` runs here
# exactly as CI does. Needs uv (brew install uv).
install:
	uv venv --clear --python 3.14 .venv
	uv pip install --python $(PY) --quiet --require-hashes -r requirements.txt
	uv pip install --python $(PY) --quiet --require-hashes -r forecast/requirements-service.txt
	uv pip install --python $(PY) --quiet bandit==1.9.4 pip-audit==2.10.1

# `.env` is read here, by the shell, and nowhere in the code: production has
# no such file (Railway injects variables), and a loader in the app would let
# a developer's local file leak into the test suite.
run:
	@set -a; [ -f .env ] && . ./.env; set +a; $(PY) server.py

test:
	$(PY) tests/test_dispatch.py

test-frontend:
	python3 tests/test_frontend.py

test-forecast:
	$(PY) tests/test_forecast.py

sweep:
	python3 tools/sweep_tree.py

# The same files and threshold as CI's blocking step, so a scan failure is
# seen before a push rather than after a deploy (a SHA-1 fingerprint once
# reached main this way). Installs the pinned scanner if it is missing.
SAST_FILES = copilot.py server.py google_mail.py google_data.py xero.py worldoptions.py recon.py mailmime.py eori.py tokenvault.py logdrain.py totp.py pipedrive.py
sast:
	@$(PY) -m bandit --version >/dev/null 2>&1 || $(PY) -m pip install --quiet bandit==1.9.4
	$(PY) -m bandit -q -lll -iii -r $(SAST_FILES)

env-doc:
	$(PY) tools/env_reference.py --write

check: test-frontend test-forecast sweep sast
	$(PY) tools/env_reference.py --check
	$(PY) tests/test_dispatch.py
