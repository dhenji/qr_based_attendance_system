export interface SyncQueueRecord {
  id: string;
  type: "attendance_scan" | "excuse_request" | "face_enrollment";
  status: "pending" | "synced" | "failed";
  payload: unknown;
  createdAt: string;
  attempts: number;
  maxAttempts: number;
}