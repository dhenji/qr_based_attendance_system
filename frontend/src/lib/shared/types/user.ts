// user.ts
// Authenticated user shape (mirrors backend auth.User); iat/exp come from JWT.
import type { AuthRole } from './auth';

export interface User {
  id: string;
  email: string;
  // Includes super_admin — deps.py treats it as a superset of admin.
  role: AuthRole;
  firstName?: string | null;
  lastName?: string | null;
  mfaEnabled?: boolean;
  mustChangePassword?: boolean;
  iat?: number;
  exp?: number;
}