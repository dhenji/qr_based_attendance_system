// timing.ts
// Timing helpers for async UI state.

export const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

// Runs `action` and guarantees it takes at least `ms` to settle, padding only
// when the action resolves sooner. The resolved value and any thrown error both
// pass through untouched, so this is safe to wrap a call whose timing the
// caller cares about but whose result must not change.
export const withMinDuration = async <T>(ms: number, action: () => Promise<T>): Promise<T> => {
  const startedAt = Date.now();
  try {
    return await action();
  } finally {
    const remaining = ms - (Date.now() - startedAt);
    if (remaining > 0) await sleep(remaining);
  }
};
