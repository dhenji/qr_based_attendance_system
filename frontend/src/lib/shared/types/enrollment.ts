export interface Enrollment {
  id: number;
  studentId: number;
  courseId: number;
  semester: string;
  yearLevel: number;
  isActive: boolean;
}