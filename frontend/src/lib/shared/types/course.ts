export interface Course {
  id: number;
  courseCode: string;
  courseName: string;
  units: number;
  semesterWeeks: number;
  scheduleDays: string[];
  scheduleStartTime: string;
  scheduleEndTime: string;
  classroomName?: string;
  classroomLat?: number;
  classroomLng?: number;
  defaultPresentWindowMinutes: number;
  defaultLateWindowMinutes: number;
  isActive: boolean;
}