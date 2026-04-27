# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This is a fresh `uv`-initialized Python 3.12 scaffold. There is no real code yet — `main.py` is a hello-world entry point, `pyproject.toml` has no dependencies, and `README.md` is empty. Treat the project as greenfield; there is no existing architecture to preserve.

## Tooling

- Package/environment manager: `uv` (indicated by `.python-version` + the `uv init` layout). Use `uv add <pkg>` to add dependencies (this updates `pyproject.toml` and the lockfile) rather than editing `pyproject.toml` by hand.
- Python: 3.12 (pinned via `.python-version`, enforced by `requires-python = ">=3.12"`).
- Run the entry point: `uv run python main.py`.
- Sync the env after pulling: `uv sync`.

No test runner, linter, or formatter is configured yet — pick one when the first real code lands rather than assuming one exists.
