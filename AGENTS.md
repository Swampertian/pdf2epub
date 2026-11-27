# pdf2epub-plus

## Purpose

Build on `pdf2epub` to convert PDFs into EPUBs using GPU acceleration and
machine learning models. The current pipeline uses Marker with Surya models
for PDF extraction, layout analysis, and OCR. It produces Markdown and images
as intermediate files before packaging an EPUB. Keep CPU conversion working
for machines without a supported GPU.

## Repository layout

- `src/` — Application code. `src/pdf2epub/` is the conversion library
  (extraction, workspace I/O, metadata, HTML, images, EPUB); `cli.py` is the
  command-line layer; nothing prompts for input. `src/main.py` is the entry point.
- `tests/` — Unit tests (pytest). They must not require marker-pdf, torch or
  model downloads; they run with only the `dev` dependency group.
- `bench/` — Performance tooling. `bench/benchmark.py` measures five phases
  separately: dependency imports, model loading, PDF-to-Markdown conversion,
  saving Markdown, metadata and images, and non-interactive EPUB generation.
  It records wall-clock time, process CPU time and average utilization,
  starting and peak RAM (RSS), and, when supported, sampled GPU utilization,
  peak process VRAM, and peak PyTorch CUDA allocation. It also reports
  conversion throughput (pages per second and seconds per page), output sizes
  and image count, and environment details. Use `--json` to save the results.
- `docker/` — Container packaging for running on other machines without
  installing Python dependencies on the host. The current Dockerfile targets
  CPU execution.
- `scripts/` — Place auxiliary Bash scripts and other development tools here
  (for example `scripts/worktree.sh`),
  not in the application code or repository root.
- `books/` — Place local development PDFs here instead of the repository root.
  Do not commit local books or generated EPUBs.

## Environment

- Dependencies are managed with uv: `pyproject.toml` declares them and
  `uv.lock` pins every package. Do not edit `requirements.txt` by hand; it is
  exported from the lock for pip users (CI checks they match):
  `uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt -o requirements.txt`.
- Create the environment with `uv sync --extra cu132` (NVIDIA GPU) or
  `uv sync --extra cpu`. `uv sync --only-group dev` is enough for tests and lint.
- After changing dependencies run `uv lock` and commit `uv.lock` together
  with `pyproject.toml` and the regenerated `requirements.txt`.

## Workflow

- Agents work in isolated git worktrees, never directly in the main checkout.
  Worktrees live in `.worktree/<task-name>/` at the repository root (ignored
  by git), one per task, on a branch with the same name (for example
  `refact/uv-migration` or `fix/remove-message`).
- Create one with `scripts/worktree.sh <task-name> [base-ref]` and remove it
  with `scripts/worktree.sh --remove <task-name> [--force]` once the work is merged or
  dropped. Use `--from-working-tree` instead of a base ref to start from the
  main checkout's uncommitted state. Each worktree gets its own `.venv`
  through `uv sync`; the git-ignored local data (`books/`, `bench/out`) is
  symlinked from the main checkout, so treat it as read-only and write
  outputs inside the worktree.
- A worktree created from a ref does not include uncommitted changes in the
  main checkout; use `--from-working-tree` when the task builds on them.
- Run every command from the worktree root, and keep all edits inside it.
  Do not touch other worktrees or the main checkout.
- Do not commit, push, or open pull requests unless the user asks.
- When done, report the worktree path, the branch, and what changed so the
  user can review and merge.

## Coding rules

- Use meaningful, consistent names for classes, variables, and functions.
- Keep functions small and focused on one responsibility. Keep CLI prompts
  and file I/O separate from transformations where practical.
- Apply DRY to repeated behavior without tightly coupling unrelated stages.
  Prefer a small shared function over a framework or premature abstraction.
- Prefer straightforward imperative code for orchestration and functional
  techniques for transformations. Use pure functions when practical and
  introduce classes only when shared state or a lifecycle makes them clearer.
- Keep model loading separate from per-document conversion so that a batch
  can reuse the same models.

## Validation

- Run `uv run pytest -q tests` and `uv run ruff check --select E9,F .`.
- From the repository root, run `uv run python src/main.py --help` (or `uv run pdf2epub --help`) to check that the
  CLI starts in the active environment.
- For a targeted conversion check, use a small local sample:
  `python src/main.py books/sample.pdf output/ --max-pages 2 --skip-epub`.
  `--skip-epub` skips the EPUB stage; check an EPUB separately when changing
  that stage.
- For performance comparisons, use the same PDF, page range, hardware, and
  model cache state. Compare the affected phase, not just the total runtime.
