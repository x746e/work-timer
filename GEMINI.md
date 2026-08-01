# Gemini AI Assistant Instructions

This file provides context and instructions for AI agents interacting with this project.

## Project Overview
**Name:** `work_timer`
**Type:** Code Project (Python Application)
**Description:** A simple terminal-based timer and task management application.
**Key Technologies:**
- **Language:** Python 3.13+
- **Package Manager:** `uv`
- **UI Framework:** `textual`
- **Core Libraries:** `pandas`, `bigtree`, `loguru`, `desktop-notifier`, `filelock`, `gcsa`

## Architecture & Structure
- `pyproject.toml` / `uv.lock`: Configuration and dependencies via `uv`.
- `src/work_timer/`: Main source code directory.
  - Contains submodules like `taskdb/`, `timer/`, `ui/`, `utils/`.
- `scripts/`: Shell scripts for running the application in various modes (dev, prod, testing).

## Building and Running
Always use `uv run` to execute commands within the project's virtual environment.

- **Run Dev App (TUI):** `./scripts/run_dev_app.sh` (Supports `-m` for memray profiling).
- **Run Dev CLI (`wtctl`):** `./scripts/run_dev_wtctl.sh [args]`
- **Run Tests:** `uv run pytest`
- **Run Linters/Typecheckers:** The project uses `ruff`, `pylint`, `pyright`, and `mypy` (configured in `pyproject.toml`). Run via `uv run <linter>`.

## Development Conventions
- **Testing:** Tests are colocated with source files using the `*_test.py` naming convention (e.g., `src/work_timer/planning_test.py`).
- **Dependencies:** Manage dependencies using `uv` (e.g., `uv add <pkg>`).
- **Typing & Linting:** Maintain strict typing and adhere to existing styling. Code should pass `ruff`, `pylint`, `pyright`, and `mypy` checks.
- **Async:** The project makes heavy use of async features (`textual`, `pytest-asyncio`). Ensure async methods are properly awaited and tested.
