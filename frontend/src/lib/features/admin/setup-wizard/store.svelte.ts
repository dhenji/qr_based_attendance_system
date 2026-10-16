// features/admin/setup-wizard/store.svelte.ts
// Guided Program -> Structure -> Offering setup state (frontend-only).
//
// The wizard reuses the existing program/course/offering services verbatim —
// no new endpoints, no backend change. This store only remembers *where the
// admin is* in the flow so the three steps stay linked (the chosen program
// flows into year/course setup, which flows into offering creation) and so a
// reload resumes instead of restarting.
//
// Persistence is a convenience, never a requirement: every storage access is
// guarded for SSR (module code also runs on the server) and wrapped in
// try/catch, so a hostile or full storage backend can never break the flow.

export type WizardStep = 1 | 2 | 3;

const STORAGE_KEY = 'attendly_setup_wizard_v1';

interface PersistedWizard {
	step: WizardStep;
	programId: number | null;
	yearLevelId: number | null;
	structureReady?: boolean;
}

export const WIZARD_STEPS: { n: WizardStep; title: string; blurb: string }[] = [
	{ n: 1, title: 'Program', blurb: 'Pick an existing program or create a new one' },
	{ n: 2, title: 'Structure', blurb: 'Add year levels and course templates' },
	{ n: 3, title: 'Offerings', blurb: 'Schedule course instances for a term' },
];

export const wizardState = $state({
	step: 1 as WizardStep,
	programId: null as number | null,
	yearLevelId: null as number | null,
	// Whether step 2's checklist (≥1 usable year with terms + ≥1 course
	// template) was last seen complete. Set by step 2 itself; step 3 stays
	// locked until then so the breadcrumb cannot skip the structure step.
	structureReady: false,
});

const canStore = (): boolean => typeof localStorage !== 'undefined';

const readPersisted = (): PersistedWizard | null => {
	if (!canStore()) return null;
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as Partial<PersistedWizard>;
		const step: WizardStep = parsed.step === 2 || parsed.step === 3 ? parsed.step : 1;
		return {
			step,
			programId: typeof parsed.programId === 'number' ? parsed.programId : null,
			yearLevelId: typeof parsed.yearLevelId === 'number' ? parsed.yearLevelId : null,
			structureReady: parsed.structureReady === true,
		};
	} catch {
		return null;
	}
};

const persist = (): void => {
	if (!canStore()) return;
	try {
		const payload: PersistedWizard = {
			step: wizardState.step,
			programId: wizardState.programId,
			yearLevelId: wizardState.yearLevelId,
			structureReady: wizardState.structureReady,
		};
		localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
	} catch {
		// Resume is a convenience; storage trouble must never break the wizard.
	}
};

// Restore the saved position. Called once from the wizard shell onMount.
// A saved step without its program is a dead end (e.g. the program was
// deleted on another tab): fall back to step 1 instead of stranding the
// admin on a step whose data cannot load. A saved step 3 without a
// completed structure checklist (e.g. storage from before the gate
// existed) falls back to step 2, which recomputes readiness on load.
export const loadWizard = (): void => {
	const saved = readPersisted();
	if (!saved) return;
	wizardState.step = saved.step;
	wizardState.programId = saved.programId;
	wizardState.yearLevelId = saved.yearLevelId;
	wizardState.structureReady = saved.structureReady ?? false;
	if (wizardState.step > 1 && wizardState.programId === null) {
		wizardState.step = 1;
	} else if (wizardState.step === 3 && !wizardState.structureReady) {
		wizardState.step = 2;
	}
};

// Steps 2 and 3 both need a chosen program; step 3 additionally needs the
// step-2 checklist (a usable year with terms plus a course template).
// Years and courses themselves are built inside step 2, and the year pick
// inside step 3 defaults to the first usable year.
export const canReachStep = (step: WizardStep): boolean => {
	if (step === 1) return true;
	if (wizardState.programId === null) return false;
	if (step === 3) return wizardState.structureReady;
	return true;
};

export const goToStep = (step: WizardStep): void => {
	if (!canReachStep(step)) return;
	wizardState.step = step;
	persist();
};

// Switching programs invalidates everything downstream (years belong to a
// program, offerings to a year), so the year pick and the structure
// checklist are cleared with it.
export const setWizardProgram = (programId: number | null): void => {
	if (wizardState.programId !== programId) {
		wizardState.yearLevelId = null;
		wizardState.structureReady = false;
	}
	wizardState.programId = programId;
	persist();
};

export const setWizardYear = (yearLevelId: number | null): void => {
	wizardState.yearLevelId = yearLevelId;
	persist();
};

// Step 2 reports its checklist here so the shell can gate step 3 on it.
// No-op when unchanged so the reporting effect never churns storage.
export const setStructureReady = (ready: boolean): void => {
	if (wizardState.structureReady === ready) return;
	wizardState.structureReady = ready;
	persist();
};

export const resetWizard = (): void => {
	wizardState.step = 1;
	wizardState.programId = null;
	wizardState.yearLevelId = null;
	wizardState.structureReady = false;
	if (!canStore()) return;
	try {
		localStorage.removeItem(STORAGE_KEY);
	} catch {
		// Same as persist: never break the flow over storage.
	}
};
