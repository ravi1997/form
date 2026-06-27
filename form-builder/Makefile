.PHONY: help install run init-db test test-auth test-vcs test-app clean

PYTHON ?= python3
PIP ?= pip3

help:
	@echo "Targets:"
	@echo "  install   Install Python dependencies"
	@echo "  run       Start the Flask app"
	@echo "  init-db   Initialize MongoDB indexes"
	@echo "  test      Run the core unittest suite"
	@echo "  test-auth Run auth/ACL tests"
	@echo "  test-vcs  Run versioning tests"
	@echo "  test-app  Run app validation tests"
	@echo "  clean     Remove local caches and runtime artifacts"

install:
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) app.py

init-db:
	$(PYTHON) db_init.py

test:
	$(PYTHON) -m unittest discover -v

test-auth:
	$(PYTHON) -m unittest -v test_auth_acl

test-vcs:
	$(PYTHON) -m unittest -v test_vcs_lifecycles

test-app:
	$(PYTHON) -m unittest -v test_app

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -path './static/uploads/*' -type f -delete

