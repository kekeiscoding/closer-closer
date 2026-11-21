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
