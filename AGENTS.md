# ISATU - SSS

Shared repository instructions for Codex and Gemini CLI. `GEMINI.md` imports this file. The project is a Flask prototype for Iloilo Science and Technology University’s student services.

## Working in this repository

- Run `git status --short --branch` before editing. Inspect overlapping diffs and preserve existing changes, including work from another agent. The working tree may contain features that have been deployed and await a Git commit.
- Keep changes focused on the requested task. Use the local setup, checks, and deployment commands in [README.md](README.md). The intended audience and demo flow are in [ISATU-SSS-Pitch-Brief.md](ISATU-SSS-Pitch-Brief.md).
- Keep credentials, SQLite data, student information, payment tokens, and local environment files out of Git and logs. Use synthetic data for tests and demos.

## Code map

| Area | Location |
| --- | --- |
| Flask app, authentication, route handlers | `sss/__init__.py` |
| Service catalog, form fields, date validation | `sss/catalog.py` |
| SQLite schema, checkout tokens, payment and issuance | `sss/db.py` |
| WebSocket status and HTTP fallback | `sss/live.py`, `frontend/payments.js` |
| QR scanning, camera selection, and form behavior | `frontend/scanner.js` |
| Templates, styles, and PDF generation | `sss/templates/`, `sss/static/style.css`, `sss/pdfs.py` |
| Workflow tests and hosting | `tests/test_workflows.py`, `Dockerfile`, `compose.yml` |

## Behavior to preserve

- The current payment QR opens `/checkout/<token>` without a login. Give that token access only to the order’s public line items, total, and simulated payment. Require student ownership or admin access for full order details, attachments, and PDFs. Require admin access to verify issued Registrar documents. Existing `/pay/<order-id>` links use student sign-in.
- Confirm payment and issue PDFs in the same SQLite transaction. Repeated confirmation must return the original payment and files. Update open request views over WebSocket, with the HTTP status endpoint as a fallback, without reloading the page.
- Validate Registrar attendance years, optional graduation date, and any grade coverage on the server. Show inconsistent older orders as needing review and block new payments on those unpaid orders. Retain existing paid records and issued PDFs so the admin can review the original. Use the Manila date for validation.
- Clinic request forms ask for a preferred date and time and derive age from date of birth. The scanner lets users select from the cameras the browser exposes, including Continuity Camera when available.
- Keep each issued Registrar copy’s document ID and QR on the first page only. Demo transcripts and diplomas carry sample markings.
- Follow [DESIGN-apple.md](DESIGN-apple.md) for interface work. Use the existing ISATU seal and credited library photograph. Source any additional photography from supplied or licensed images.

## Verification and deployment

- Prioritize deployment speed and keep testing very limited: run only the minimal check needed for the change (e.g., `npm run build` for frontend edits or a quick targeted check) and avoid heavy browser walkthroughs or full verification suites unless explicitly requested.
- Run `npm run build` for frontend changes. Only run `.venv/bin/python -m pytest` or local browser checks when needed for risky workflow, camera, or WebSocket changes.
- Review `git status --short` and `git diff --check` before handoff. Report the commands run and any verification limits.
- The deployed app uses the `isatu-sss` Compose project and a persistent SQLite volume. Keep the volume across releases and use the loopback service or a container-local health check for verification. The Cloudflare Tunnel origin uses Docker service DNS at `http://isatu-sss:1133`. See the README for deployment details.
