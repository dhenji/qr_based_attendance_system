// enrollment.ts
// Links a student to a course offering for a given academic year/semester.
export interface Enrollment {
  id: number;
  studentId: number;
  offeringId: number;
  academicYear: string;
  semester: string;
}