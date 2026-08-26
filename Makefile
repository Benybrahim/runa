.PHONY: install format lint typecheck test check clean

install:
	uv sync

format:
	uv run ruff format

lint:
	uv run ruff check

lint-fix:
	uv run ruff check --fix

typecheck:
	uv run pyright

test:
	uv run pytest

check:
	$(MAKE) format
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test

clean:
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .pyright
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info