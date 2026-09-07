// features/auth/store.svelte.ts
// Auth session state using Svelte 5 runes ($state object store)

import type { User } from '$lib/shared/types';
import { browser } from '$app/environment';
import { login, logout } from '$lib/features/auth/service';

// Auth state as a single reactive object
export const authState = $state({
	user: null as User | null,
	loading: false,
	error: null as string | null,
});

// Derived flags (functions — module-scope $derived cannot be exported)
export const isAuthenticated = () => !!authState.user;
export const isStudent = () => authState.user?.role === 'student';
export const isProfessor = () => authState.user?.role === 'professor';
export const isAdmin = () => authState.user?.role === 'admin';

// Restore session from localStorage on first load (browser only)
if (browser) {
	const stored = localStorage.getItem('auth_user');
	if (stored) {
		try {
			authState.user = JSON.parse(stored);
		} catch {
			localStorage.removeItem('auth_user');
		}
	}
}

// Persist user to localStorage (browser only) — explicit, call after mutations.
const persistUser = () => {
	if (!browser) return;
	if (authState.user) {
		localStorage.setItem('auth_user', JSON.stringify(authState.user));
	} else {
		localStorage.removeItem('auth_user');
	}
};

// Actions
export const doLogin = async (email: string, password: string): Promise<void> => {
	authState.loading = true;
	authState.error = null;
	try {
		const result = await login(email, password);
		authState.user = result.user;
		persistUser();
	} catch (e: unknown) {
		authState.error = e instanceof Error ? e.message : 'Login failed';
		throw e;
	} finally {
		authState.loading = false;
	}
};

export const doLogout = async (): Promise<void> => {
	await logout();
	authState.user = null;
	persistUser();
};
