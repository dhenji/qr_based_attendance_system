// features/admin/schema.ts
// Zod schemas for the admin roster forms. Mirrors the backend validators in
// features/student/schema.py and features/professor/schema.py (lengths,
// email normalisation); the backend remains the source of truth for 409s
// (duplicate email/code) and FK errors (unknown program/year).

import { z } from 'zod';

const nameField = z.string().trim().min(1, 'Required').max(100);
const emailField = z.string().trim().toLowerCase().email('Enter a valid email').max(255);

export const adminStudentCreateSchema = z.object({
	student_id: z.string().trim().toUpperCase().min(3).max(50),
	first_name: nameField,
	middle_name: z.string().trim().max(100).optional().or(z.literal('')),
	last_name: nameField,
	email: emailField,
	program_id: z.coerce.number().int().positive('Pick a program'),
	year_level_id: z.coerce.number().int().positive('Pick a year level'),
	section: z.string().trim().max(50).optional().or(z.literal('')),
	username: z.string().trim().min(3).max(150).optional().or(z.literal('')),
});

export type AdminStudentCreateInput = z.infer<typeof adminStudentCreateSchema>;

export const adminStudentUpdateSchema = z.object({
	first_name: nameField.optional(),
	last_name: nameField.optional(),
	email: emailField.optional(),
	program_id: z.coerce.number().int().positive().optional(),
	year_level_id: z.coerce.number().int().positive().optional(),
	section: z.string().trim().max(50).optional().or(z.literal('')),
	is_active: z.boolean().optional(),
});

export type AdminStudentUpdateInput = z.infer<typeof adminStudentUpdateSchema>;

export const adminProfessorCreateSchema = z.object({
	first_name: nameField,
	middle_name: z.string().trim().max(100).optional().or(z.literal('')),
	last_name: nameField,
	email: emailField,
	department: z.string().trim().max(100).optional().or(z.literal('')),
	username: z.string().trim().min(3).max(150).optional().or(z.literal('')),
	courses: z.array(z.coerce.number().int().positive()).default([]),
});

export type AdminProfessorCreateInput = z.infer<typeof adminProfessorCreateSchema>;

export const adminProfessorUpdateSchema = z.object({
	first_name: nameField.optional(),
	last_name: nameField.optional(),
	email: emailField.optional(),
	department: z.string().trim().max(100).optional().or(z.literal('')),
	is_active: z.boolean().optional(),
	courses: z.array(z.coerce.number().int().positive()).optional(),
});

export type AdminProfessorUpdateInput = z.infer<typeof adminProfessorUpdateSchema>;

export const csvFileSchema = z
	.instanceof(File, { message: 'Choose a CSV file' })
	.refine((f) => f.name.toLowerCase().endsWith('.csv'), 'File must end in .csv')
	.refine((f) => f.size > 0, 'File is empty')
	.refine((f) => f.size <= 5 * 1024 * 1024, 'File must be under 5 MB');

// Face-enrollment photo (D43 3-photo upload: front/left/right). Mirrors the
// backend quality gates loosely client-side (type + non-empty + size); the
// server owns brightness/face-size/single-face/sharpness/eyes-open checks.
export const facePhotoSchema = z
	.instanceof(File, { message: 'Choose a photo' })
	.refine(
		(f) => ['jpg', 'jpeg', 'png', 'webp'].some((ext) => f.name.toLowerCase().endsWith(`.${ext}`)),
		'Photo must be JPG, PNG, or WebP'
	)
	.refine((f) => f.size > 0, 'Photo is empty')
	.refine((f) => f.size <= 5 * 1024 * 1024, 'Photo must be under 5 MB');

// Admin user create (super_admin only). Mirrors backend
// features/admin/schema.py AdminUserCreate: creatable roles are
// admin/professor/student — super_admin is seeded, never created via API.
export const adminUserCreateSchema = z.object({
	email: emailField,
	role: z.enum(['admin', 'professor', 'student'], {
		message: 'Pick a role',
	}),
	first_name: nameField,
	middle_name: z.string().trim().max(100).optional().or(z.literal('')),
	last_name: nameField,
	username: z.string().trim().min(3).max(150).optional().or(z.literal('')),
});

export type AdminUserCreateInput = z.infer<typeof adminUserCreateSchema>;
