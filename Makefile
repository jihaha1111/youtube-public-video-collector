PYTHON ?= python3.11
VENV_PYTHON := .venv/bin/python

.PHONY: venv install test mock

venv:
	$(PYTHON) -m venv .venv

install: venv
	$(VENV_PYTHON) -m pip install -e ".[dev]"

test:
	$(VENV_PYTHON) -m pytest

mock:
	$(VENV_PYTHON) -m yt_collector.cli collect \
		--url "https://www.youtube.com/watch?v=onjVWrO2_5E" \
		--limit 3 \
		--format json \
		--out output/result.json \
		--mock
