.PHONY: install format lint typecheck test check hello examples clean

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
#	$(MAKE) typecheck
	$(MAKE) test

hello:
	uv run python examples/hello.py

examples:
	uv run python examples/hello.py
	uv run python examples/hello_anthropic.py
	uv run python examples/conversation.py
	uv run python examples/background.py
	uv run python examples/approval.py
	uv run python examples/eval.py
	uv run python examples/delegate.py
	uv run python examples/plan_and_review.py
	uv run python examples/streaming.py

clean:
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .pyright
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info