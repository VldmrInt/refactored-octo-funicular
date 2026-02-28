VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

.PHONY: venv install test

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt

test: install
	$(PYTEST) tests/ -v
