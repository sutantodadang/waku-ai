import type { ReactNode } from "react";

export function Spinner() {
  return (
    <div className="flex justify-center py-10">
      <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-brand-tint border-t-brand" />
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-2xl bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-100">
      <span aria-hidden>⚠️</span>
      <span>{message}</span>
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-[20px] bg-white p-5 ring-1 ring-ink/[0.06] shadow-[0_1px_3px_rgba(12,31,23,0.05)] ${className}`}>
      {children}
    </div>
  );
}

export function PageTitle({ children }: { children: ReactNode }) {
  return <h1 className="mb-4 font-display text-2xl font-extrabold tracking-tight text-ink">{children}</h1>;
}

const VARIANTS: Record<string, string> = {
  primary: "bg-accent text-white shadow-[0_2px_10px_rgba(255,90,54,0.28)]",
  secondary: "bg-brand text-white shadow-[0_2px_10px_rgba(0,168,132,0.22)]",
  ghost: "bg-white text-ink ring-1 ring-ink/10",
  danger: "bg-white text-red-600 ring-1 ring-red-200",
};

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex min-h-[2.75rem] w-full items-center justify-center gap-1.5 rounded-2xl px-4 text-sm font-semibold transition active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-ink/70">{label}</span>
      {children}
    </label>
  );
}

// text-base (16px) keeps iOS Safari from zooming on focus.
export const inputCls =
  "w-full min-h-[2.75rem] rounded-2xl border border-ink/10 bg-white px-3.5 text-base text-ink outline-none transition placeholder:text-ink/35 focus:border-brand focus:ring-2 focus:ring-brand/20";
