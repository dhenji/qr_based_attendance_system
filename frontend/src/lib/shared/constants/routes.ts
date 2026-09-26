// routes.ts
// Central URL map so pages navigate with named constants instead of raw strings.
export const Routes = {
  HOME: "/",
  AUTH: "/auth",
  LOGIN: "/auth/login",
  REGISTER: "/auth/register",
  FORGOT_PASSWORD: "/auth/forgot-password",
  STUDENT: "/student",
  DASHBOARD: "/student/dashboard",
  SCAN: "/student/scan",
  HISTORY: "/student/history",
  SCHEDULE: "/student/schedule",
  PROFILE: "/student/profile",
  SETTINGS: "/student/settings",
  PROFESSOR: "/professor",
  PROFESSOR_DASHBOARD: "/professor/dashboard",
  PROFESSOR_COURSES: "/professor/courses",
  PROFESSOR_SESSIONS: "/professor/sessions",
  PROFESSOR_SESSIONS_CREATE: "/professor/sessions/create",
  PROFESSOR_SESSIONS_HISTORY: "/professor/sessions/history",
  PROFESSOR_ATTENDANCE: "/professor/attendance",
  PROFESSOR_EXCUSE_REQUESTS: "/professor/excuse-requests",
  PROFESSOR_REPORTS: "/professor/reports",
  PROFESSOR_PROFILE: "/professor/profile",
  PROFESSOR_SETTINGS: "/professor/settings",
  // No /admin route exists yet (admin portal is Phase 3) — kept for future use.
  ADMIN: "/admin",

  ABOUT: "/about",
  PRIVACY_POLICY: "/privacy-policy",
  COOKIES: "/cookies",
};

// The active-session (projector) route is parameterised by session id, so it
// gets a builder rather than a constant.
export const professorActiveSession = (id: number): string =>
  `${Routes.PROFESSOR_SESSIONS}/active/${id}`;

// The create form has two variants (D11): the locked one is entered from a
// course card and arrives with the offering pre-selected and read-only; the
// bare path is the selector variant entered from the dashboard.
export const professorSessionCreate = (offeringId?: number): string =>
  offeringId === undefined
    ? Routes.PROFESSOR_SESSIONS_CREATE
    : `${Routes.PROFESSOR_SESSIONS_CREATE}?offering=${offeringId}`;