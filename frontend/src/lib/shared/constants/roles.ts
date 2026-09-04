export const Roles = {
  SUPER_ADMIN: "super_admin" as const,
  ADMIN: "admin" as const,
  PROFESSOR: "professor" as const,
  STUDENT: "student" as const,
};

export type UserRole = keyof typeof Roles;