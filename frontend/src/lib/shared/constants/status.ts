// status.ts
// Attendance + offline-sync status enums, mirroring src/shared/enums.py.
export const AttendanceStatus = {
  PRESENT: "present" as const,
  LATE: "late" as const,
  ABSENT: "absent" as const,
  EXCUSED: "excused" as const,
  REJECTED: "rejected" as const,
};

export type AttendanceStatus = keyof typeof AttendanceStatus;

export const SyncStatus = {
  PENDING: "pending" as const,
  SYNCED: "synced" as const,
  FAILED: "failed" as const,
};

export type SyncStatusValue = keyof typeof SyncStatus;