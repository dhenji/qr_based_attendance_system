// shared/utils/entityEvents.ts
// Typed in-memory pub/sub for admin entity changes (issue #221).
//
// Admin list/detail pages share module-level $state stores but have no
// cache, polling, or push channel: a mutation refreshes only the store it
// touched, so sibling pages (list <-> archive, pickers, joins) stay stale
// until a manual reload. Mutators call notifyEntityChanged() after a
// successful write; mounted pages subscribeEntity() to the entities they
// render and re-fetch (own entity -> refresh*(), lookup entity -> reload
// picker options only). Credential-only resets stay silent by design.
//
// Pure callbacks, no store imports (no import cycles). Delivery is
// synchronous over a snapshot; a throwing listener never blocks the rest
// (fail-soft). No timers, no network, no backend change.

export type AdminEntity =
	| 'students'
	| 'professors'
	| 'users'
	| 'programs'
	| 'courses'
	| 'offerings'
	| 'dashboard'
	| 'settings';

type EntityListener = () => void;

const listeners = new Map<AdminEntity, Set<EntityListener>>();

export const notifyEntityChanged = (entity: AdminEntity): void => {
	const subs = listeners.get(entity);
	if (!subs || subs.size === 0) return;
	// Snapshot: subscribe/unsubscribe during delivery must not skip or
	// double-fire listeners.
	for (const cb of [...subs]) {
		try {
			cb();
		} catch {
			// One bad subscriber must not break the rest. Errors surface
			// through the subscriber's own store/page error state.
		}
	}
};

export const subscribeEntity = (entity: AdminEntity, cb: EntityListener): (() => void) => {
	let subs = listeners.get(entity);
	if (!subs) {
		subs = new Set();
		listeners.set(entity, subs);
	}
	subs.add(cb);
	return () => {
		subs.delete(cb);
		if (subs.size === 0) listeners.delete(entity);
	};
};
