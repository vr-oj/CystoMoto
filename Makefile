SHELL := /bin/zsh

PYTHON := ./.cystomoto/bin/python
ifeq ($(wildcard $(PYTHON)),)
PYTHON := python3
endif

.PHONY: check-qt run qt-repair

check-qt:
	$(PYTHON) scripts/check_qt_runtime.py --strict

run: check-qt
	$(PYTHON) cysto_app/cysto_app.py

qt-repair:
	$(PYTHON) scripts/repair_qt_env.py --reinstall
