// features/auth/store.svelte.ts
// Auth session state using Svelte 5 runes ($state object store)

import type { User } from '$lib/shared/types';
import { browser } from '$app/environment';
import { login, logout } from '$lib/features/auth/service';

// Auth state (rune-store)
// Single reactive object holding the current user, loading flag, and last error.
export const authState = $state({
	user: null as User | null,
	loading: false,
	error: null as string | null,
});

// Derived role helpers
// Plain functions (module-scope $derived cannot be exported) used to guard UI.
export const isAuthenticated = () => !!authState.user;
export const isStudent = () => authState.user?.role === 'student';
export const isProfessor = () => authState.user?.role === 'professor';
export const isAdmin = () => authState.user?.role === 'admin';

// Session restore & persistence (browser only)
// On server/first load we have no session; in the browser we rehydrate the user
// from localStorage so a refresh keeps you logged in.
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
// doLogin calls the auth service, then caches the user locally on success.
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
