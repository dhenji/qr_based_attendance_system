# Face Enrollment Guide

> QR-Based Attendance System — Operator Guide for Face Enrollment
>
> Covers: 3-photo capture operator script, common failures, privacy considerations.
>
> **Glossary**: All italicized terms are defined in the [Glossary](../project/glossary.md).
>
> **Route**: `/admin/face-enrollment/{student_id}` ([D28](../project/decision-log.md), [D43](../project/decision-log.md))

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Step-by-Step Operator Script](#3-step-by-step-operator-script)
4. [Quality Gates & Common Failures](#4-quality-gates--common-failures)
5. [What Happens After Capture](#5-what-happens-after-capture)
6. [Re-Enrollment Policy](#6-re-enrollment-policy)
7. [Privacy Script for Students](#7-privacy-script-for-students)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Overview

Face enrollment captures **3 photos** (front, left, right) per student ([D43](../project/decision-log.md)). The server generates a **128-dimensional face embedding** from each photo using a pretrained face-api.js ResNet model. The three vectors are stored as a single encrypted JSON blob in `students.face_embedding BYTEA` ([D28](../project/decision-log.md)):

```json
{
  "mean": [128 floats],
  "angles": {
    "front": [128 floats],
    "left": [128 floats],
    "right": [128 floats]
  }
}
```

- **`mean`**: Average of the three vectors — used for primary comparison during scan
- **`angles`**: Per-angle vectors — used for tie-breaking in borderline cases
- **Version**: `face_embedding_version` bumps on every write

> **Enrollment is mandatory** for face-based liveness verification. Students without an enrolled embedding cannot complete Step 4 of the scan flow.

---

## 2. Prerequisites

| Requirement             | Details                                                    |
| ----------------------- | ---------------------------------------------------------- |
| **Admin access**        | You must have an admin or super_admin role                 |
| **Student record**      | The student must exist in the system with `is_active=true` |
| **Camera**              | Device camera (front-facing preferred) or USB webcam       |
| **Lighting**            | Well-lit room; face should not be in shadow                |
| **Student cooperation** | Student must be present and willing                        |

---

## 3. Step-by-Step Operator Script

### 3.1 Open the Enrollment Screen

1. Navigate to **Admin Portal** → **Student Management** (`/admin/students`)
2. Search for the student by name or ID
3. Click the student row → **Student Detail**
4. Click **[📷 Enroll Face]** or navigate to `/admin/face-enrollment/{student_id}`

[FIG: Face Enrollment screen with student name/ID header, three capture slots (Front, Left, Right), camera preview area, quality indicators, [Capture] button, [Save Enrollment] button]

### 3.2 Capture Position 1: Front

1. Instruct the student to:
   - Face the camera directly
   - Keep eyes open, neutral expression
   - Remove glasses if possible (or keep them on — system accommodates)
   - Ensure forehead and chin are visible
2. Click **[Capture]** when the quality gate passes:
   - ✅ Brightness: adequate
   - ✅ Face size: fills >30% of frame
   - ✅ Single face detected
3. The photo is stored as `front`

### 3.3 Capture Position 2: Left

1. Instruct the student to:
   - Turn head ~30–45 degrees to their **left**
   - Keep eyes open
   - Maintain same distance from camera
2. Click **[Capture]** when quality gates pass
3. The photo is stored as `left`

### 3.4 Capture Position 3: Right

1. Instruct the student to:
   - Turn head ~30–45 degrees to their **right**
   - Keep eyes open
   - Maintain same distance from camera
2. Click **[Capture]** when quality gates pass
3. The photo is stored as `right`

### 3.5 Review & Save

1. Review all three captured photos (thumbnail previews)
2. If any photo looks poor, click **[Retake]** for that position
3. Click **[Save Enrollment]**
4. Server generates embeddings → stores encrypted blob → bumps `face_embedding_version`
5. Student sees "✅ Enrolled" status on their Profile (`/student/profile`)

> **Distribution**: The student's device will pull the new embedding on their next login ([D29](../project/decision-log.md) — pull-on-login, version-gated, cached encrypted in IndexedDB).

---

## 4. Quality Gates & Common Failures

### 4.1 Quality Gate Criteria

| Gate            | Threshold                                                       | How to Fix                                  |
| --------------- | --------------------------------------------------------------- | ------------------------------------------- |
| **Brightness**  | Face region must be adequately lit (not over/under-exposed)     | Move to better lighting; avoid backlighting |
| **Face Size**   | Face must occupy >30% of the frame                              | Move student closer to camera               |
| **Single Face** | Only one face detected in frame                                 | Ensure no one else is in the shot           |
| **Pose**        | Head not turned beyond acceptable angle for the target position | Adjust head position                        |
| **Eyes Open**   | Both eyes must be open (EAR threshold)                          | Ask student to open eyes fully              |

### 4.2 Common Failures & Solutions

| Failure                   | Cause                                              | Solution                                              |
| ------------------------- | -------------------------------------------------- | ----------------------------------------------------- |
| "Face not detected"       | Face too small; poor lighting; face angled too far | Reposition; improve lighting; ensure face is centered |
| "Multiple faces detected" | Another person in frame                            | Ensure only the student is in the shot                |
| "Image too dark"          | Under-lit room                                     | Move to brighter area; use additional lighting        |
| "Image too bright"        | Over-exposed; direct sunlight                      | Avoid direct sunlight; use diffused lighting          |
| "Eyes appear closed"      | Blinking; low eyelid opening                       | Ask student to keep eyes open; capture again          |
| "Pose mismatch"           | Head angle doesn't match target position           | Adjust head angle; refer to guide illustrations       |
| "Blur detected"           | Motion blur; out of focus                          | Hold still; ensure camera is focused on face          |

### 4.3 Retry Policy

- No limit on retakes per position — quality gates must pass before saving
- If a student repeatedly fails (e.g., due to medical condition), note this in the admin audit log and contact development team for manual embedding generation

---

## 5. What Happens After Capture

### 5.1 Embedding Generation (Server-Side)

1. Three photos uploaded as multipart form data
2. Server runs each through **pretrained face-api.js ResNet** model (we train nothing — [D43](../project/decision-log.md))
3. Generates 128-dimensional vector per photo
4. Computes `mean` (average of three vectors)
5. Stores encrypted JSON blob in `students.face_embedding BYTEA`
6. Sets `face_enrolled_at` timestamp
7. Increments `face_embedding_version`

### 5.2 Embedding Distribution

| Step                  | What Happens                                                    |
| --------------------- | --------------------------------------------------------------- |
| Student logs in       | Device checks `face_embedding_version` against cached version   |
| New version available | Device downloads embedding via `GET /student/me/face-embedding` |
| Cached in IndexedDB   | Stored encrypted with device-specific WebCrypto key             |
| Used in Step 4        | Local comparison for offline verification                       |

### 5.3 Encryption

- **At rest**: Stored as BYTEA in PostgreSQL (encrypted at the application level)
- **On device**: Cached encrypted in IndexedDB (WebCrypto device key)
- **In transit**: HTTPS only

---

## 6. Re-Enrollment Policy

### 6.1 When to Re-Enroll

| Trigger                           | Action                                                                              |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| **Student requests**              | Admin initiates new enrollment — supersedes old vectors                             |
| **Significant appearance change** | Admin re-enrolls — old embedding replaced                                           |
| **Admin archive**                 | Embedding revoked (student deactivated/archived)                                    |
| **Version bump**                  | Every re-enrollment increments `face_embedding_version`; devices pull on next login |

### 6.2 How to Re-Enroll

1. Navigate to `/admin/face-enrollment/{student_id}`
2. Existing enrollment status is shown (enrolled date, version)
3. Click **[Re-Enroll]** — this will **replace** the old embedding
4. Capture 3 new photos following the standard script
5. Save → old vectors are discarded; new blob stored; version bumped

> **No rollback**: Re-enrollment permanently replaces the old embedding. Previous scan records retain their original `face_match_score` values.

---

## 7. Privacy Script for Students

Use this script when explaining face enrollment to students:

---

> **What we collect**: Three photos of your face (front, left, right) during enrollment. These are converted into a mathematical representation (a face embedding) and stored encrypted in our database.
>
> **What we do with it**: During attendance scanning, the system compares your live face against this stored representation to verify your identity. This prevents someone else from scanning on your behalf.
>
> **What we do NOT do**:
>
> - We do **not** store the raw photos after enrollment — only the mathematical embedding
> - We do **not** share your face data with any third party
> - We do **not** use your face data for any purpose other than attendance verification
> - We do **not** track your face outside of scan sessions
>
> **Your rights**:
>
> - You may request re-enrollment at any time (contact admin)
> - Your embedding is removed if you are deactivated or archived
> - All data is encrypted at rest and in transit
>
> **Storage**: Embeddings are stored encrypted in `students.face_embedding` (BYTEA). Your device caches a copy encrypted in IndexedDB for offline verification. Both copies are encrypted with industry-standard AES-256-GCM.
>
> **Questions?** Contact your administrator or refer to the [Face Enrollment Architecture](../architecture/face-enrollment.md) for technical details.

---

## 8. Troubleshooting

| Issue                                    | Cause                                                | Solution                                              |
| ---------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------- |
| Camera not working                       | Browser permissions                                  | Grant camera permission; check browser settings       |
| "Upload failed"                          | Network error; file too large                        | Retry; ensure stable connection; check file size      |
| "Student not found"                      | Wrong student ID                                     | Verify student ID; check student is active            |
| Embedding not updating on student device | Version mismatch; student hasn't logged in           | Ask student to log out and back in; check version     |
| Borderline score (0.65–0.70) in scan     | Embedding may need refresh                           | Re-enroll the student with updated photos             |
| Sibling confusion                        | Known limitation ([D31](../project/decision-log.md)) | Not currently solved; acknowledge as known limitation |

---

## Quick Reference: Key Routes & Endpoints

| Task                         | Route / Endpoint                                                   |
| ---------------------------- | ------------------------------------------------------------------ |
| Admin: Enroll Face           | `/admin/face-enrollment/{student_id}` (UI)                         |
| API: Upload 3 photos         | `POST /admin/face-enrollment/{student_id}` (multipart)             |
| API: Check enrollment status | `GET /admin/face-enrollment/{student_id}`                          |
| Student: Pull embedding      | `GET /student/me/face-embedding` (version-gated)                   |
| Architecture docs            | [Face Enrollment Architecture](../architecture/face-enrollment.md) |

---

_For the full technical specification of the embedding format, verification thresholds, and evidence bundle schema, see the [Face Enrollment Architecture](../architecture/face-enrollment.md) and [Security Model](../architecture/security-model.md)._

