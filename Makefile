.PHONY: test lint check help

help:
	@echo "Comandos disponibles:"
	@echo "  make test       Ejecutar tests con pytest"
	@echo "  make lint       Revisar código con ruff"
	@echo "  make check      Ejecutar tests + linting"

test:
	.venv/bin/python -m pytest tests/ -v

lint:
	.venv/bin/ruff check generar_mapa.py

check: lint test
	@echo "✓ Todo bien"
