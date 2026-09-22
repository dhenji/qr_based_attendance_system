// sync.ts
// Offline queue entry (docs/architecture/offline-first.md); payload holds the
// original action data until it syncs or exhausts its retry budget.
export interface SyncQueueRecord {
  id: string;
  type: "attendance_scan" | "excuse_request" | "face_enrollment";
  status: "pending" | "synced" | "failed";
  payload: unknown;
  createdAt: string;
  attempts: number;
  maxAttempts: number;
}