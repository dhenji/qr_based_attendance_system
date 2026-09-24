// student.ts
// Student profile; links to a User via userId (1:1) and tracks face enrollment.
// Mirrors backend feature/student/model.py + the GET /student/profile contract.
// New-field values arrive from the backend API when the student endpoints land;
// the fields mirroring backend columns stay optional until then.
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