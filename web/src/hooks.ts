import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

export interface Poll<T> {
  data: T | undefined;
  error: Error | undefined;
  refresh: () => Promise<void>;
}

/** Fetch now, then every `intervalMs` while the tab is visible. Pass 0 to fetch once. */
export function usePoll<T>(fetcher: () => Promise<T>, intervalMs: number): Poll<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    try {
      setData(await fetcherRef.current());
      setError(undefined);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (!intervalMs) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [refresh, intervalMs]);

  return { data, error, refresh };
}

// -- Minimal history-based routing (the app has two pages and a handful of tabs) --------------

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((fn) => fn());
window.addEventListener("popstate", notify);

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function navigate(to: string) {
  if (to === window.location.pathname) return;
  window.history.pushState(null, "", to);
  window.scrollTo(0, 0);
  notify();
}

export function usePath(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}

/** Re-render every `ms` so relative timestamps stay fresh. */
export function useNow(ms = 15_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(timer);
  }, [ms]);
  return now;
}
