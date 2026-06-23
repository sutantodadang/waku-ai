import { dismiss, useToasts, type Toast } from "../lib/toast";

const TYPE_CLS: Record<Toast["type"], string> = {
  success: "bg-brand text-white shadow-[0_2px_10px_rgba(0,168,132,0.30)]",
  error:   "bg-accent text-white shadow-[0_2px_10px_rgba(255,90,54,0.30)]",
  info:    "bg-ink text-white shadow-[0_2px_10px_rgba(12,31,23,0.22)]",
};

export default function Toaster() {
  const toasts = useToasts();
  if (!toasts.length) return null;

  return (
    <div
      aria-live="polite"
      className="fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 pointer-events-none"
    >
      {toasts.map((t) => (
        <button
          key={t.id}
          role="status"
          onClick={() => dismiss(t.id)}
          className={`pointer-events-auto max-w-sm w-full rounded-2xl px-4 py-3 text-sm font-semibold text-left ring-1 ring-white/10 transition active:scale-[0.98] ${TYPE_CLS[t.type]}`}
        >
          {t.message}
        </button>
      ))}
    </div>
  );
}
