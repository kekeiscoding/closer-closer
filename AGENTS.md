# Closer Closer

These instructions apply throughout this repository and are shared by Codex and Gemini CLI.

## Working in this repository

- Run `git status --short --branch` before editing. Preserve existing changes, including work from another agent. If edits overlap, inspect the diff before proceeding.
- Keep changes focused on the requested task. Once the project has a README and build configuration, follow the setup commands and conventions documented there.
- Keep credentials and local environment files out of Git. Use placeholders in any example configuration.

## Verification

- Run the relevant tests, lint, or build checks defined by the project. Report which commands ran and any checks that were unavailable.
- Review `git status --short` and `git diff --check` before handing off. If you add new files, inspect them too because unstaged diffs omit untracked files.
- Update this file when the project gains a stack, a directory layout, and standard development commands. Gemini CLI loads these instructions through `GEMINI.md`.

## Stack and commands

- `sss/` contains the Flask routes, server-rendered templates, SQLite persistence, and ReportLab PDF generation.
- `frontend/scanner.js` contains the QR scanner and form behavior. Run `npm ci` and `npm run build` to bundle it.
- Set up Python with `python3 -m venv .venv` and `.venv/bin/python -m pip install -r requirements-dev.txt`. Run the app with `.venv/bin/python -m flask --app sss run --port 8000`.
- Run `.venv/bin/python -m pytest` for the request, payment, and PDF checks in `tests/`. The README documents QR testing and the Docker deployment.
