"use client";

// Bottom-right notification stack, modelled after the Tailwind UI
// "Successfully saved!" pattern. Up to 3 toasts visible at once; new
// arrivals push older ones up the stack. Each toast auto-dismisses
// after TIMEOUT_MS, with the timer paused while the cursor is hovering
// over it so the operator can finish reading before it disappears.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastVariant = "success" | "error" | "info" | "warning";

interface ToastItem {
  id: number;
  variant: ToastVariant;
  title: string;
  description?: string;
}

interface ToastApi {
  push: (variant: ToastVariant, title: string, description?: string) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
  warning: (title: string, description?: string) => void;
}

const Ctx = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const c = useContext(Ctx);
  if (!c) throw new Error("useToast must be inside <ToastProvider>");
  return c;
}

const MAX_VISIBLE = 3;
const TIMEOUT_MS = 3000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const push = useCallback(
    (variant: ToastVariant, title: string, description?: string) => {
      idRef.current += 1;
      const id = idRef.current;
      // Keep at most MAX_VISIBLE — drop the OLDEST so the freshest
      // notification is the one the operator sees.
      setItems((prev) => [...prev, { id, variant, title, description }].slice(-MAX_VISIBLE));
    },
    [],
  );

  const remove = useCallback(
    (id: number) => setItems((prev) => prev.filter((t) => t.id !== id)),
    [],
  );

  const api: ToastApi = {
    push,
    success: (t, d) => push("success", t, d),
    error: (t, d) => push("error", t, d),
    info: (t, d) => push("info", t, d),
    warning: (t, d) => push("warning", t, d),
  };

  return (
    <Ctx.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col-reverse gap-2"
      >
        {items.map((t) => (
          <ToastRow key={t.id} item={t} onClose={() => remove(t.id)} />
        ))}
      </div>
    </Ctx.Provider>
  );
}

function ToastRow({
  item,
  onClose,
}: {
  item: ToastItem;
  onClose: () => void;
}) {
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const t = window.setTimeout(onClose, TIMEOUT_MS);
    return () => window.clearTimeout(t);
  }, [paused, onClose]);

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      role="status"
      className="pointer-events-auto w-full max-w-sm overflow-hidden rounded-lg bg-white shadow-lg ring-1 ring-black/5 dark:bg-zinc-900 dark:ring-white/10"
    >
      <div className="p-4">
        <div className="flex items-start">
          <div className="shrink-0">{iconFor(item.variant)}</div>
          <div className="ml-3 w-0 flex-1 pt-0.5">
            <p className="text-sm font-medium text-foreground">{item.title}</p>
            {item.description && (
              <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
            )}
          </div>
          <div className="ml-4 flex shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex rounded-md text-muted-foreground hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <span className="sr-only">Close</span>
              <svg viewBox="0 0 20 20" fill="currentColor" className="size-5" aria-hidden="true">
                <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function iconFor(variant: ToastVariant) {
  const className = "size-6";
  if (variant === "success") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={`${className} text-emerald-500`} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
      </svg>
    );
  }
  if (variant === "error") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={`${className} text-red-500`} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
      </svg>
    );
  }
  if (variant === "warning") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={`${className} text-amber-500`} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={`${className} text-sky-500`} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
    </svg>
  );
}
