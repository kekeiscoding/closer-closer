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

Open [localhost:8000](http://localhost:8000). Use this same origin when scanning QR codes. On another port, set `APP_BASE_URL` to the new local origin before starting the server. The app stores its database and session key under the ignored `instance/` directory.

### Demo flow

1. Sign in as a student, choose OSAS or Registrar, and submit a request. Save the order ID or order QR.
2. In Cashier, open the simulated LANDBANK checkout link or scan its QR and complete the demo payment. For in-person payment, sign in as admin and confirm the order in Admin Cashier.
3. Download the paid PDFs from My requests. Sign in as admin and enter a Registrar document ID or upload an image of its first-page QR to view the issuance record and retrieve the original.
4. Use sample data when demonstrating the clinic and clearance fields. The university documents and payments generated here are prototype outputs.

## Checks

```sh
npm run build
.venv/bin/python -m pytest
git diff --check
```

## Deploy to the Docker host

Copy the build context to the release directory on the server. From that directory, run `docker compose -p isatu-sss up -d --build --wait`. Compose publishes the service on loopback port 1133 and connects to the existing `cloudflare-tunnel_default` network. Set `ISATU_HOST_PORT` in the server's ignored `.env` if the default port is occupied. The `isatu-sss_app-data` volume stores all requests, attachments, issued PDFs, and the session key between releases.

The configured app origin is `https://hackathon.bisakol.com`. In the existing Cloudflare Tunnel, add this hostname as a published application route with service URL `http://isatu-sss:1133`. The service keeps the same internal port even if the host port changes. Set the final origin before issuing documents because the stored PDFs contain URLs from the time they were issued.
