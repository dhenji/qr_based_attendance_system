export interface User {
  id: string;
  email: string;
  role: "admin" | "professor" | "student";
  iat?: number;
  exp?: number;
}