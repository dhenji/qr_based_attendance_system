# Face Enrollment Guide

> QR-Based Attendance System — Operator Guide for Face Enrollment
>
> Covers: 3-photo upload or live-camera capture, enrollment status, current limitations, privacy wording.
>
> **Glossary**: All italicized terms are defined in the [Glossary](../project/glossary.md).
>
> **Route**: `/admin/students` → **Enroll face** modal ([D28](../project/decision-log.md), [D43](../project/decision-log.md)). There is no dedicated `/admin/face-enrollment/{student_id}` page.

> **Current build status (2026-11-02):** enrollment generates a real 512-d
> embedding (MobileFaceNet ONNX, landmark fallback), stored plaintext; scans
> compare the server-generated live embedding via cosine similarity. Encryption
> at rest is not implemented. See
> [face-enrollment.md](../architecture/face-enrollment.md) §4 and ADR-068.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Step-by-Step Operator Script](#3-step-by-step-operator-script)
4. [Validation & Common Failures](#4-validation--common-failures)
5. [What Happens After Upload](#5-what-happens-after-upload)
6. [Re-Enrollment Policy](#6-re-enrollment-policy)
7. [Privacy Script for Students](#7-privacy-script-for-students)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Overview

Face enrollment accepts **3 image files** (front, left, right) per student
([D43](../project/decision-log.md)). The server generates a real 512-d
`FACEEMB1` embedding and writes it to `students.face_embedding`
([D28](../project/decision-log.md)):

- **Embedding**: 512-d vector generated server-side (MobileFaceNet ONNX,
  landmark fallback).
- **Version**: the `students.face_embedding_version` column increments on every
  upload (`FACE_EMBEDDING_VERSION`, currently `1`).
- **Encryption**: The database blob is plaintext today. The student's
  browser caches a pulled copy with AES-GCM in IndexedDB.

> **Enrollment is not required to scan.** Students without an enrollment can
> complete liveness and submit attendance. The scan never reads
> `students.face_embedding`, so do not tell students that their face is being
> compared.

---

## 2. Prerequisites

| Requirement             | Details                                                    |
| ----------------------- | ---------------------------------------------------------- |
| **Admin access**        | You must have an admin or super_admin role                 |
| **Student record**      | The student must exist in the system with `is_active=true` |
| **Three image files**   | Front, left, and right photos (`.jpg`, `.jpeg`, `.png`, or `.webp`) |
| **File size**           | Each file must be below `ATTACHMENTS_MAX_BYTES`            |
| **Student cooperation** | Student must consent to the upload                         |
| **Camera (optional)**   | For the live-capture mode the operator's browser needs camera permission and a secure context (HTTPS or localhost) |

The admin UI supports two capture methods: selecting three files from disk, or
opening the live camera and following guided on-screen prompts to capture the
front, left, and right angles automatically.

---

## 3. Step-by-Step Operator Script

### 3.1 Open the Enrollment Modal

1. Navigate to **Admin Portal** → **Student Management** (`/admin/students`).
2. Search for the student by name or ID.
3. Click **[📷 Enroll face]** (or **[Re-enroll face]** if already enrolled).
4. The enrollment modal shows the current status (enrolled date and version)
   and three file inputs.

[FIG: Enroll Face modal with Front / Left / Right file inputs or live camera view, mode toggle, current status, error/note area, and Upload enrollment button]

### 3.2 Select the Photos (file upload)

1. **Front**: a straight-on photo.
2. **Left**: the student's head turned to their left.
3. **Right**: the student's head turned to their right.
4. The UI accepts JPG, JPEG, PNG, and WebP files only.

### 3.2a Live camera capture (alternative)

1. In the enrollment modal click **[Use camera]** instead of **[Upload files]**.
2. Allow camera access when prompted.
3. The camera opens with a guide oval and an on-screen instruction for the
   current angle (front → left → right).
4. Hold the pose until the progress bar fills; the frame is captured
   automatically. Use **[Capture now]** to capture manually when aligned.
5. After each capture a review panel opens with **[Use Photo]** and **[Retake Photo]**.
   - **[Use Photo]** commits the captured frame and advances to the next angle
     (front → left → right → complete), disabling auto-capture so you can
     reposition before the next angle.
   - **[Retake Photo]** restarts the camera stream cleanly for the same angle
     and resets auto-capture to off.
6. After all three angles are committed the modal returns to the file view with
   the three images populated and uploads them through the same endpoint.
   The live preview is mirrored for natural selfie framing; captured images
   are stored unmirrored.
7. Use **[Upload files]** to switch back to manual selection at any time.
8. An "Automatically capture when aligned" checkbox gates auto-capture per
   session; it resets to off on every retake and when advancing angles.

> The server now runs brightness, face-size, single-face, centering, sharpness,
> and eyes-open checks via `shared/face_quality.py`. Bad photos are rejected with
> `invalid_image`, `no_face_detected`, `multiple_faces`, or `quality_too_low`.

### 3.3 Upload & Verify

1. Click **[Upload enrollment]** (or finish a camera capture) and confirm the
   **confirmation overlay** that opens ("Confirm face enrollment upload" /
   "Remove face enrollment?").
2. The server validates that each file is non-empty, within the size limit, and
   has an `image/*` content type.
3. On success, the modal shows `Enrolled (vN)` and the roster **Face** column
   updates after refresh.
4. The student's Profile (`/student/profile`) and Settings
   (`/student/settings`) show **Enrolled** and the version.

> **Distribution**: The student's browser can pull the blob on login
> ([D29](../project/decision-log.md) — pull-on-login, version-gated) and caches
> it encrypted in IndexedDB. Nothing compares it.

---

## 4. Validation & Common Failures

### 4.1 What the Server Checks

| Check             | Current behavior                                      |
| ----------------- | ----------------------------------------------------- |
| **Non-empty file**| Rejected with 400 `invalid_image`                     |
| **Size limit**    | Rejected with 400 `invalid_image` when over the limit |
| **Content type**  | Must start with `image/`; otherwise 400 `invalid_image` |
| **Student exists**| 404 `student_not_found`                               |
| **Face detection**| 400 `no_face_detected` when no face is found |
| **Multiple faces**| 400 `multiple_faces` when more than one face is found |
| **Quality/pose**  | 422 `quality_too_low` for brightness, size, centering, sharpness, or eyes-open failures |

### 4.2 Common Failures & Solutions

| Failure                   | Cause                                              | Solution                                              |
| ------------------------- | -------------------------------------------------- | ----------------------------------------------------- |
| "Upload failed"           | Network error; file too large; wrong content type  | Retry; check file size and that it is JPG/PNG/WebP    |
| "Student not found"       | Wrong student ID; archived student                 | Verify the student is active                          |
| "Photo is empty"          | Selected file has no content                       | Re-select a valid image                               |
| Faculty reports no match  | **No matching exists in this build**               | Explain that only liveness runs; escalate as a product gap |

---

## 5. What Happens After Upload

### 5.1 Server-Side Processing

1. Three files arrive as multipart form data.
2. The server validates non-empty content, size, and `image/*` content type.
3. **No ResNet inference runs.** `_stub_embedding_blob` writes the zero-filled
   JSON shown in §1.
4. Sets `face_enrolled_at` and increments `face_embedding_version`.
5. Writes an audit row for the enrollment metadata. The blob itself is excluded
   from the audit snapshot.

### 5.2 Distribution & Use

| Step                  | What Happens                                                    |
| --------------------- | --------------------------------------------------------------- |
| Student logs in       | Device checks `face_embedding_version` against its cached version |
| New version available | Device downloads the blob via `GET /student/me/face-embedding`   |
| Cached in IndexedDB   | Stored with a device-specific WebCrypto AES-GCM key              |
| Used in the scan      | **No** — the scan never reads the cached blob                    |

### 5.3 Encryption

- **Server at rest**: Plaintext real 512-d embedding; application-level encryption
  is **not implemented**.
- **On device**: The cached copy is AES-GCM encrypted with a non-extractable
  device key.
- **In transit**: HTTPS in production.

---

## 6. Re-Enrollment Policy

### 6.1 When to Re-Enroll

| Trigger                           | Action                                                                              |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| **Student requests**              | Admin opens the same modal and uploads three new files                              |
| **Significant appearance change** | Re-upload — the embedding is replaced                                             |
| **Admin archive**                 | Blob is cleared and the student is deactivated                                      |
| **Version bump**                  | Every upload increments `face_embedding_version`; devices may pull on next login    |

### 6.2 How to Re-Enroll

1. Navigate to `/admin/students`.
2. Open the student's **[Re-enroll face]** action.
3. Upload three new images (or capture them via the live camera).
4. Submit — the old embedding is discarded and the version is bumped.

### 6.3 How to Remove an Enrollment

1. Open the student's **[Enroll face]** / **[Re-enroll face]** modal.
2. If the student is currently enrolled, click **[Remove enrollment]**.
3. Confirm the prompt. The stored blob is cleared, `face_enrolled_at` is
   nulled, and `face_embedding_version` is incremented so device caches drop
   their copy.

> **No rollback**: Re-enrollment replaces the stored embedding. Previous attendance
> records are unaffected.

---

## 7. Privacy Script for Students

Use this script when explaining enrollment to students:

---

> **What we collect**: Three photos of your face (front, left, right) are
> uploaded for enrollment.
>
> **What we store today**: The server generates a real face embedding (a
> 512-d vector) from your photos and stores it in the database (plaintext
> today; encryption at rest is not implemented). The uploaded photos are not
> retained by the application.
>
> **What we do with it**: During attendance, the server compares your live
> face to the stored embedding. Attendance also uses a liveness challenge
> (blink and head turns) and GPS.
>
> **What we do NOT do**:
>
> - We do **not** store the raw photos after the upload request completes
> - We do **not** share your face data with any third party
> - We do **not** track your face outside of scan sessions
>
> **Your rights**:
>
> - You may request re-enrollment at any time (contact admin)
> - Your enrollment is cleared if your account is archived (not merely toggled inactive)
> - The device cache is encrypted in transit and at rest in IndexedDB
>
> **Storage**: The server holds a real face embedding in
> `students.face_embedding` (plaintext today). Your browser may cache a pulled
> copy encrypted with AES-GCM.
>
> **Questions?** Contact your administrator or refer to the
> [Face Enrollment Architecture](../architecture/face-enrollment.md) for
> technical details.

---

## 8. Troubleshooting

| Issue                                    | Cause                                                | Solution                                              |
| ---------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------- |
| "Upload failed"                          | Network error; file too large; wrong content type    | Retry; check file size and image type                 |
| "Student not found"                      | Wrong student ID; archived student                   | Verify student ID; check the student is active        |
| Enrollment status not visible            | Roster not refreshed                                 | Refresh the students page                             |
| Student device has an old version        | Version mismatch; student has not logged in          | Ask the student to log out and back in                |
| Faculty expects a face match             | **Not implemented** in this build                    | Explain the gap; do not promise biometric matching    |
| "No face detected" / "too many faces"    | Backend quality gate rejected the photo (detection/multiple faces) | Retake the named photo with one face centered and well lit |
| "Image quality too low"                  | Backend quality gate (brightness/size/centering/sharpness/eyes) | Retake the named photo; improve lighting and hold still |
| "Something went wrong. Please try again." (HTTP 500) | Unexpected server error; previously an `UnboundLocalError` in `FaceEnrollmentService.enroll_face` | Retry; if it persists, check server logs and the captured photo |

---

## Quick Reference: Key Routes & Endpoints

| Task                         | Route / Endpoint                                                   |
| ---------------------------- | ------------------------------------------------------------------ |
| Admin: Enroll Face           | `/admin/students` → **Enroll face** modal (no dedicated page)      |
| API: Upload 3 photos         | `POST /admin/face-enrollment/{student_id}` (multipart)             |
| API: Check enrollment status | `GET /admin/face-enrollment/{student_id}`                          |
| Student: Pull embedding      | `GET /student/me/face-embedding` (version-gated)                   |
| Architecture docs            | [Face Enrollment Architecture](../architecture/face-enrollment.md) |

---

_For the embedding format, current limitations (encryption at rest), and the
matching pipeline, see the [Face Enrollment Architecture](../architecture/face-enrollment.md)
and [Security Model](../architecture/security-model.md)._
