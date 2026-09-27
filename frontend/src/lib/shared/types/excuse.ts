// excuse.ts
// Professor excuse-queue view-model (mock-only, Path A/B/C per D21).
//
// Mirrors the GET /professor/excuse-requests contract item in camelCase:
// `status` maps excuse_requests.status (pending/approved/rejected),
// `initiatedVia` maps excuse_requests.initiated_via
// (quick | prof_with_evidence | request), `originalStatus` is the preserved
// attendance_records.validation_status before the excuse (D22).
export type ExcuseStatus = 'pending' | 'approved' | 'rejected';

export type ExcuseInitiatedVia = 'quick' | 'prof_with_evidence' | 'request';

export type ExcuseOriginalStatus = 'absent' | 'late' | 'rejected';

export interface ExcuseRequest {
  id: number;
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
