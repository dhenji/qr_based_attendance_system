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
  PROFESSOR_SESSIONS: "/professor/sessions",
  // No /admin route exists yet (admin portal is Phase 3) — kept for future use.
  ADMIN: "/admin",

  ABOUT: "/about",
  PRIVACY_POLICY: "/privacy-policy",
  COOKIES: "/cookies",
};