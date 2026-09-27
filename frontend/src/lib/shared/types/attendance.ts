// attendance.ts
// One scan result. scannedVia tells how it was captured; gps + optional
// faceMatchScore back the proof stored with the record.
export interface AttendanceRecord {
  id: number;
  sessionId: number;
  studentId: string;
  studentNumber: string;
  // D15 roster statuses. The student scan path only ever produces
  // present/late/rejected; absent/excused/pending appear on professor views.
  status: "present" | "late" | "absent" | "excused" | "pending" | "rejected";
  scannedAt?: string;
  scannedVia: "qr" | "gps" | "face";
  faceMatchScore?: number;
  gps?: {
    lat: number;
    lng: number;
    accuracy: number;
  };
  excuseReason?: string;
  // Professor ledger enrichments (contract GET /professor/attendance shape).
  // Optional so scan-path records stay valid without them.
  studentName?: string;
  courseCode?: string;
  courseName?: string;
  section?: string;
  sessionCode?: string;
  createdAt?: string;
  originalStatus?: Exclude<AttendanceRecord["status"], "excused">;
}