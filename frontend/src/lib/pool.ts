/**
 * Run `fn` over `items` with at most `limit` calls in flight.
 *
 * Fleet-wide actions (refresh all, bulk firmware upgrade) go through the
 * existing per-device endpoints so each device keeps its own permission
 * check and audit row. This keeps them from opening a hundred router
 * sessions at once. `fn` must not throw — callers record per-item errors
 * themselves.
 */
export async function runPool<T>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<void>,
): Promise<void> {
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const item = items[next++];
      await fn(item);
    }
  });
  await Promise.all(workers);
}

/** Strip a RouterOS channel suffix: "7.16.1 (stable)" → "7.16.1". */
export function normFw(v: string | null | undefined): string {
  if (!v) return "";
  return v.replace(/\s*\([^)]*\)\s*$/, "").trim();
}
