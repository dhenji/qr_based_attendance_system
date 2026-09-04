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