# ISATU - SSS

Iloilo Science and Technology University Student Services System. The prototype covers OSAS and Registrar requests, online payment simulation, in-person payment recording, PDF downloads, and Registrar document verification.

## Run locally

Requires Python 3.12+ and Node.js 22+. Use the demo accounts supplied for the project. Student passwords are the exact surnames from their profiles.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
npm run build
.venv/bin/python -m flask --app sss run --port 8000
```

Open [localhost:8000](http://localhost:8000). On another port, set `APP_BASE_URL` to the browser origin before starting the server. The app embeds that origin in checkout and verification QR codes. For a second-device demo, use an HTTPS origin the device can reach. A QR for `localhost` opens on the device that scans it.

The app stores its SQLite database and session key under the ignored `instance/` directory. Set `ISATU_DATA_DIR` to a separate directory when running a disposable demo or testing an upgrade.

### Student accounts

Students can sign up with a profile and password. The app assigns an ID using the Manila year, a random four-digit number, and an A, U, or I suffix. The account-created page displays the ID before the student proceeds to sign in. Students can change passwords in their account menu. Admins manage students, reset passwords to their current surname, deactivate access, and permanently delete deactivated accounts and their associated data.

Existing demo students are migrated into SQLite once with their existing credentials. New students receive a consistent randomized sample transcript at their first transcript payment.

### Demo flow

1. Sign in as a student, choose OSAS or Registrar, and submit a request. The receipt shows the order ID, a payment QR, and a completed request-form PDF for printing before payment.
2. Scan the QR on another device or open the checkout link. The guest checkout shows the requested items and total, and the only action needed to pay is the simulated LANDBANK Pay button. For an in-person payment, enter the order ID in Admin Cashier.
3. Keep the receipt or My requests open to see payment confirmation and downloads update over WebSocket. Paid PDFs and attachments are available to the signed-in student and admin.
4. To verify a Registrar document, sign in as admin and enter its ID, scan its QR, or upload an image of the first page. In the scanner, use the Camera menu to select an available device. An iPhone appears when the operating system makes Continuity Camera available to the browser.
5. Use sample data in clinic forms and clearance uploads. The university documents and payments generated here are prototype outputs.

Registrar requests validate attendance, graduation and grade coverage together. Grade coverage uses the attendance years and any graduation date as bounds. The demo treats August, January and June as the start months of the first semester, second semester and summer term. Inconsistent older requests are flagged for review, and those awaiting payment require a corrected submission.

## Checks

```sh
npm run build
.venv/bin/python -m pytest
git diff --check
```

The workflow suite covers role access, guest checkout and CSRF, payment idempotency, Registrar date validation, existing orders, and PDF issuance. For a browser check, keep the student receipt and My Requests open, then pay from a separate signed-out browser context using the payment QR link. Confirm the receipt and downloads update without navigation. For camera changes, check device switching and QR image upload.

Request-form PDFs use the four supplied DOCX forms exported as templates in `sss/form_templates/`. The app fills them from the saved order and places the order ID in the footer. Payment receipt and staff fields are left for the university to complete. Paid Registrar documents keep their separate verification IDs and QR codes.

## Payment routes

| Route | Access and purpose |
| --- | --- |
| `/checkout/<token>` | Guest checkout. Shows the public line items, order ID, and amount. Records the simulated payment on Pay. |
| `/checkout/<token>/status/live` | Guest WebSocket. Sends whether that checkout has been paid. `/checkout/<token>/status` is the HTTP fallback. |
| `/payments/status/live` | Signed-in WebSocket. Sends paid order IDs visible to the active account. `/payments/status` is the HTTP fallback. |
| `/pay/<order-id>` | Compatibility route for signed-in student checkout. |
| `/verify/<document-id>` | Admin-only lookup for the original issued Registrar PDF. |

## Deploy to the Docker host

The release directory on the server is `/opt/isatu-sss`. The Docker build uses `Dockerfile`, `.dockerignore`, the Python and Node manifests and lockfile, `frontend/`, and `sss/`. The runtime also needs `compose.yml`. From the release directory, run the following after copying the updated build context.

```sh
docker compose -p isatu-sss up -d --build --wait
docker compose -p isatu-sss ps
curl -fsS http://127.0.0.1:1133/healthz
```

Compose publishes the app on loopback port 1133. Set `ISATU_HOST_PORT` in the server’s ignored `.env` if the host port changes, and update the loopback health check command accordingly. Keep the `isatu-sss_app-data` volume across releases. It stores the SQLite database, payment links, attachments, issued PDFs, and session key.

The configured public origin is [hackathon.bisakol.com](https://hackathon.bisakol.com). The Cloudflare Tunnel route uses `http://isatu-sss:1133` on the shared `cloudflare-tunnel_default` Docker network. A route aimed at the host’s LAN address will return connection refused with the loopback port mapping. Set `APP_BASE_URL` to the final HTTPS origin before issuing documents because stored PDFs keep the verification URLs they were issued with.

Gunicorn uses threaded workers for WebSocket connections. When changing proxy or deployment settings, verify that signed-in payment status connects through WebSocket with the forwarded HTTPS scheme and the public Host header.

## Image credit

The library photograph on the sign-in and overview screens is by Patrik Göthe. [Unsplash photo](https://unsplash.com/photos/xiTFENI0dMY)
