// user.ts
// Authenticated user shape (mirrors backend auth.User); iat/exp come from JWT.
export interface User {
  id: string;
  email: string;
  role: "admin" | "professor" | "student";
  iat?: number;
  exp?: number;
}