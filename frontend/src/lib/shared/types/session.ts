// session.ts
// Attendance session a professor opens. qrPayload is embedded in the QR code;
// pw/lw are the present and late windows. `students` is the live scan feed.
export interface Session {
  id: number;
  courseId: number;
  code: string;
  qrPayload: {
    v: number;
    code: string;
    course: number;
    radius: number;
    pw: number;
    lw: number;
  };
  expiresAt: string;
  scheduledEndTime: string;
  createdAt: string;
  presentCount: number;
  lateCount: number;
  absentCount: number;
  status: "active" | "closed";
  students: Array<{
    studentId: string;
    name: string;
    section: string;
    status: "present" | "late" | "absent" | "excused" | "rejected";
    scannedAt?: string;
  }>;
}