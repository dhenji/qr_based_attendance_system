// student.ts
// Student profile; links to a User via userId (1:1) and tracks face enrollment.
export interface Student {
  id: string;
  userId: string;
  studentNumber: string;
  firstName: string;
  middleName?: string;
  lastName: string;
  programCode: string;
  yearLevelLabel: string;
  section: string;
  faceEnrolled: boolean;
  isActive: boolean;
}