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
| OSAS | The Office of Student Affairs and Services handles ID and lanyard issuance and replacement, medical appointment requests, and dental appointment requests. The forms capture relevant checklist items, preferred appointment details, and consent. Each request costs ₱50 and produces a completed request PDF after payment. |
| Registrar | Students can request one or more document types, choose copy quantities, and pay ₱50 per copy. Certification of Grades requires a start and end academic year and semester. Good Moral requests require a clearance attachment. |
| Cashier | Students can look up an order by ID or QR code. The simulated LANDBANK checkout opens in a separate tab and shows the line items and total before the student presses Pay. For in-person payments, the admin finds the order and records payment. |
| My Requests | Students can see pending order IDs and payment status. Paid requests show a separate download for each copy. |
| Admin tools | Admin can review all student submissions, record in-person payments, and verify Registrar documents by entering a document ID or scanning the QR. |

**Registrar catalog.** Transcript of Records, Diploma, Good Moral, Certification of Graduation, Certification of Grades, Certification of Units Earned, Certification of Enrollment, DFA/CHED Authentication of Student’s Records, and Others (Specify).

## How a request becomes a verifiable PDF

1. A student chooses an office and service, completes the form using their prefilled profile, and submits it.
2. The portal displays **Request received** with an order ID, an order QR code, and a **Pay** button. One Registrar order can contain several document types and copies.
3. Cashier looks up the order and shows the amount due. Confirming a simulated online payment or recording an in-person payment releases the PDFs.
4. The student opens **My Requests** to download the files. Diploma and Transcript of Records downloads are clearly labeled samples. The remaining Registrar services produce completed request-form PDFs.
5. Each paid Registrar copy has its own document ID and a QR at the bottom of page one. The admin uses it to find the issuance record and retrieve the original file stored by the system.

The **order ID** tracks the request and payment. The **document ID** identifies a specific issued Registrar copy. The payment QR opens checkout. The document QR opens the admin verification record.

## Build and deployment status

- **Interface.** The current responsive release follows the repository’s Apple design reference with slim black navigation, flat white and charcoal surfaces, and Action Blue controls. On mobile, request lists show the order ID, payment status, and total together.
- **Implementation.** Flask serves the app, SQLite stores orders and issued files, ReportLab produces the PDFs, and ZXing reads QR codes from a camera or uploaded image. The server checks role and ownership. Payment and PDF issuance are recorded together so a repeated confirmation does not issue duplicate files.
- **Deployment.** The current Docker release was healthy on the host’s port 1133 when checked on November 21, 2026. The configured public address is [hackathon.bisakol.com](https://hackathon.bisakol.com). Public access depends on the Cloudflare Tunnel route. The confirmed deployment check was internal.
- **Verification.** Nine automated tests passed. Chrome walkthroughs exercised desktop and mobile navigation, both payment paths, QR lookup, PDF downloads, and Registrar document verification. The QR upload check decoded 20 generated order codes.

## Suggested pitch and live demo

Open with the student and cashier handoff, then show how the same order connects submission, payment, download, and verification. Use one order for **one Diploma and one Certification of Grades** as the live example. Choose the grade coverage, show the ₱100 total in Cashier, complete the simulated payment, and download both PDFs. Switch to the admin view and scan the Diploma’s first-page QR to retrieve the stored original.

For the deck, use these screens in sequence.

1. **Student overview** showing OSAS, Registrar, and Cashier.
2. **Registrar request** showing document selection and the grade coverage fields.
3. **Cashier and demo checkout** showing the order ID and itemized total.
4. **My Requests and sample PDF** showing the paid downloads and verification footer.
5. **Admin verification** showing the issuance record and original PDF link.

Present online payments as simulated, clinic schedules as preferences submitted for follow-up, and sample academic records as prototype outputs. Describe the benefits as intended workflow improvements. The project evidence supports an implemented prototype and verified test flows.
