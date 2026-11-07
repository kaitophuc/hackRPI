PYTHON ?= python3
NODE ?= node

.PHONY: run test package

run:
	$(PYTHON) server.py

test:
	$(PYTHON) -m unittest discover -s tests -v
	$(NODE) --test tests/control.test.mjs tests/game.test.mjs

# Archive the committed source, excluding Git metadata and ignored runtime files.
package:
	mkdir -p dist
	git archive --format=zip --prefix=aero-escape-run/ --output=dist/aero-escape-run.zip HEAD
