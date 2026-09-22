// attendance.ts
// One scan result. scannedVia tells how it was captured; gps + optional
// faceMatchScore back the proof stored with the record.
export interface AttendanceRecord {
  id: number;
  sessionId: number;
  studentId: string;
  studentNumber: string;
  status: "present" | "late" | "rejected";
  scannedAt: string;
  scannedVia: "qr" | "gps" | "face";
  faceMatchScore?: number;
  gps: {
    lat: number;
    lng: number;
    accuracy: number;
  };
  excuseReason?: string;
}