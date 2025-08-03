#!/usr/bin/make -f
-include makefile.local

ifndef PYTHON
PYTHON:=python3
endif
VERSION := $(shell grep -m 1 version pyproject.toml | tr -s ' ' | tr -d '"' | tr -d "'" | cut -d' ' -f3)
BAD_HTML := $(shell grep -rn sebastien docs/example/|cut -d':' -f1|uniq)

.PHONY: venv tests build example docs

venv:
	${PYTHON} -m venv venv
	./venv/bin/pip install -e .
	./venv/bin/pip install -e .[dev]
	./venv/bin/pip install -e .[doc]
	./venv/bin/pip install -e .[pdf]
	./venv/bin/pip install -e .[text]
	./venv/bin/pip install -e .[analyse]
	./venv/bin/pip install -e .[whois]
	./venv/bin/pip install -e .[bsky]
	./venv/bin/pip install -e .[build]

example:
	cd example && make clean
	cd example && make html
	rm -rf docs/example
	cp -rf example/_build/html docs/example

docs-full: example docs
	cp -rf example/_build/html docs/_build/html/example

coverage:
	-./venv/bin/coverage combine
	./venv/bin/coverage report --include sphinxcontrib/osint

docs:
	cd docs && make clean
	cd docs && make html
	for F in ${BAD_HTML}; do sed -i -e 's|/home/sebastien/devel/OSInt/sphinxcontrib-osint/example|example|g' $$F; done
	cp -rf docs/example docs/_build/html/example

build:
	rm -rf dist
	./venv/bin/python3 -m build

testpypi:
	./venv/bin/python3 -m twine upload --repository testpypi --verbose dist/*

pypi:
	./venv/bin/python3 -m twine upload --repository pypi --verbose dist/*

ruff:
	./venv/bin/ruff check sphinxcontrib/

#~ tests: tests/test_cofferfile_fernet.py tests/test_naclfile_fernet.py
tests:
	./venv/bin/pytest  --random-order tests/

release:
	sed -i -e "s/release = '.*'/release = '${VERSION}'/" docs/conf.py
	-git commit -m "Update version in doc" docs/conf.py
	-git push
	gh release create v${VERSION}

serve:
	cd example/_build/html/ && ../../../venv/bin/python3 -m http.server 8888
