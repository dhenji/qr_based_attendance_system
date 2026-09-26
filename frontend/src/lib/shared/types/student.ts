// student.ts
// Student domain types.
//
// `Student` is the camelCase view-model used across the UI. `StudentProfile` and
// `StudentDashboard` are the raw snake_case wire shapes from
// docs/architecture/api-contracts.md ("Profile & Settings", "Dashboard
// Summaries") — services map them to view-models.
export interface Student {
  id: string;
  userId: string;
  studentNumber: string;
  email?: string;
  firstName: string;
  middleName?: string;
  lastName: string;
  programCode: string;
  programName?: string;
  yearLevelLabel: string;
  section?: string;
  faceEnrolled: boolean;
  faceEnrolledAt?: string;
  faceEmbeddingVersion?: number;
  createdAt?: string;
  scanCount?: number;
  isActive: boolean;
}

// GET /student/profile
export interface StudentProfileResponse {
  student_number: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  email: string;
  program_code: string;
  year_level_label: string;
  section: string | null;
  is_active: boolean;
  face_enrolled: boolean;
  face_enrolled_at: string | null;
  face_embedding_version: number;
  created_at: string;
  scan_count: number;
}

// GET /student/dashboard
export interface StudentDashboardResponse {
  compliance_rate: number;
  scans_today: number;
  total_scans: number;
  today_schedule: unknown[];
  recent_activity: unknown[];
}
