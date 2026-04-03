.PHONY: install test lint clean

install:
	pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check .

format:
	ruff format .

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
