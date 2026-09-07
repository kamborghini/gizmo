# The developer's entry points. Every command a person runs against this repo
# is here, so nothing lives only in somebody's memory.
#
#   make install        create .venv and install the pinned requirements
#   make run            start the app on :8000, loading .env if there is one
#   make test           the dispatch suite (about a minute, no network)
#   make test-frontend  the static guards on the single-page app (seconds)
#   make check          everything CI runs that needs no network
#   make env-doc        regenerate docs/ENVIRONMENT.md from the code

PY ?= .venv/bin/python

.PHONY: help install run test test-frontend sweep env-doc check

help:
	@sed -n '4,10p' Makefile

install:
	python3 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r requirements.txt

# `.env` is read here, by the shell, and nowhere in the code: production has
# no such file (Railway injects variables), and a loader in the app would let
# a developer's local file leak into the test suite.
run:
	@set -a; [ -f .env ] && . ./.env; set +a; $(PY) server.py

test:
	$(PY) tests/test_dispatch.py

test-frontend:
	python3 tests/test_frontend.py

sweep:
	python3 tools/sweep_tree.py

env-doc:
	$(PY) tools/env_reference.py --write

check: test-frontend sweep
	$(PY) tools/env_reference.py --check
	$(PY) tests/test_dispatch.py
