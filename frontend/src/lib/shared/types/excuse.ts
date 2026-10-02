// excuse.ts
// Professor excuse-queue view-model (D21 Paths A/B/C).
//
// Mirrors the GET /professor/excuse-requests contract item in camelCase:
// `status` maps excuse_requests.status (pending/approved/rejected),
// `initiatedVia` maps excuse_requests.initiated_via
// (quick | prof_with_evidence | request). `originalStatus` is the preserved
// attendance_records.validation_status before the excuse (D22) — the live
// list row does not carry it, so real-mode rows read `unknown` (mock rows
// keep concrete values).
export type ExcuseStatus = 'pending' | 'approved' | 'rejected';

export type ExcuseInitiatedVia = 'quick' | 'prof_with_evidence' | 'request';

export type ExcuseOriginalStatus = 'absent' | 'late' | 'rejected' | 'unknown';

export interface ExcuseRequest {
  id: number;
  // Integer roster ids from the bare list row. studentId feeds the
  // per-record excuse paths (quick/edit/revoke need it in the URL);
  // studentNumber stays the display string (`#<id>` fallback in real mode).
  studentId: number;
  studentNumber: string;
  studentName: string;
  section: string;
  courseCode: string;
  courseName: string;
  sessionId: number;
  sessionCode: string;
  sessionDate: string;
  initiatedVia: ExcuseInitiatedVia;
  reason: string;
  status: ExcuseStatus;
  originalStatus: ExcuseOriginalStatus;
  requestedAt: string;
  reviewedAt?: string;
  reviewNotes?: string;
  attachmentNames: string[];
}
