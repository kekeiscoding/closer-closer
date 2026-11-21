# ISATU - SSS System Overview

**Pitch deck source brief · November 21, 2026**

ISATU - SSS is a working web prototype for Iloilo Science and Technology University’s Student Services System. Students can submit service requests, pay the cashier, track their orders, and download completed PDFs. Administrators can review submissions, record in-person payments, and verify issued Registrar documents.

## The workflow problem

A student service request has several handoffs. The student fills out a form, the cashier needs a reference to collect payment, and the office needs a way to trace the resulting document back to its issuance record. ISATU - SSS gives the student one place to follow those steps and gives staff a shared order record to work from.

The prototype demonstrates three practical benefits.

- **Students** can see what to fill out, how much they owe, and when a PDF is ready to download.
- **Cashier staff** can enter an order ID and review the requested items and total before recording payment.
- **Administrators** can retrieve the original Registrar PDF tied to a document ID and compare it with the copy being presented.

## What the prototype supports

| Area | Implemented capabilities |
| --- | --- |
| Sign-in | One portal with separate student and admin views. The demo has three student accounts and one admin account. Student profiles prefill identity, student ID, course and section, and college where applicable. |
| OSAS | The Office of Student Affairs and Services handles ID and lanyard issuance and replacement, medical appointment requests, and dental appointment requests. Clinic forms ask for one preferred date and time and derive age from date of birth. Each request costs ₱50 and produces a completed request PDF after payment. |
| Registrar | Students can request one or more document types, choose copy quantities, and pay ₱50 per copy. The app validates academic dates against attendance and graduation. Certification of Grades requires a start and end academic year and semester. Good Moral requests require a clearance attachment. |
| Cashier | Scanning the payment QR opens the simulated LANDBANK checkout, where a guest can review the line items and press Pay without signing in. For in-person payments, the admin finds the order by ID and records payment. |
| My Requests | The student’s receipt and request list update over WebSocket when payment is confirmed. Paid requests show a separate download for each copy. |
| Admin tools | Admin can review all student submissions, record in-person payments, and verify Registrar documents by entering a document ID or scanning the QR. |

**Registrar catalog.** Transcript of Records, Diploma, Good Moral, Certification of Graduation, Certification of Grades, Certification of Units Earned, Certification of Enrollment, DFA/CHED Authentication of Student’s Records, and Others (Specify).

## How a request becomes a verifiable PDF

1. A student chooses an office and service, completes the form using their prefilled profile, and submits it.
2. The portal displays **Request received** with an order ID, a payment QR, and online and in-person options. One Registrar order can contain several document types and copies.
3. A phone can scan the QR and complete the simulated payment without a student session. An admin can also record an in-person payment from the order ID.
4. Payment confirmation and PDFs appear on the open student receipt and in **My Requests** without a page refresh. Diploma and Transcript of Records downloads are clearly labeled samples. The remaining Registrar services produce completed request-form PDFs.
5. Each paid Registrar copy has its own document ID and a QR at the bottom of page one. The admin uses it to find the issuance record and retrieve the original file stored by the system.

The **order ID** tracks the request and payment. The **document ID** identifies a specific issued Registrar copy. The payment QR opens checkout. The document QR opens the admin verification record.

## Build and deployment status

- **Interface.** The responsive release follows the repository’s Apple design reference with a photo-led overview, slim black navigation, white and charcoal surfaces, and Action Blue controls. Mobile request lists show the order ID, payment status, and total together.
- **Implementation.** Flask serves the app, SQLite stores orders and issued files, ReportLab produces the PDFs, and ZXing reads QR codes from a selectable camera or uploaded image. Flask-Sock delivers payment status over WebSocket. Payment and PDF issuance happen together so a repeated confirmation does not issue duplicate files.
- **Deployment.** The current Docker release was healthy on the host’s port 1133 when checked on November 21, 2026. The configured public address is [hackathon.bisakol.com](https://hackathon.bisakol.com). Public access depends on the Cloudflare Tunnel route. The confirmed deployment check was internal.
- **Verification.** Fourteen automated tests passed. Chrome walkthroughs exercised guest checkout, camera switching with simulated feeds, and live updates for both payment paths. The deployed WebSocket was verified internally using the tunnel’s forwarded HTTPS headers.

## Suggested pitch and live demo

Open with the student and cashier handoff, then show how the same order connects submission, payment, download, and verification. Request **one Diploma and one Certification of Grades**. Choose the grade coverage and leave the receipt open. Scan the payment QR on another device, show the ₱100 total, and press Pay. Watch the downloads appear on the student’s open screen. Switch to the admin view and scan the Diploma’s first-page QR to retrieve the stored original.

For the deck, use these screens in sequence.

1. **Student overview** showing OSAS, Registrar, and Cashier.
2. **Registrar request** showing document selection and the grade coverage fields.
3. **Cashier and demo checkout** showing the order ID and itemized total.
4. **My Requests and sample PDF** showing the paid downloads and verification footer.
5. **Admin verification** showing the issuance record and original PDF link.

Present online payments as simulated, clinic schedules as preferences submitted for follow-up, and sample academic records as prototype outputs. Describe the benefits as intended workflow improvements. The project evidence supports an implemented prototype and verified test flows.
