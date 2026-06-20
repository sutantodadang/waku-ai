import type { ReactNode } from "react";

export function Spinner() {
  return (
    <div className="flex justify-center py-10">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-orange" />
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="rounded-xl bg-red-50 p-3 text-sm text-red-700">😅 {message}</div>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl bg-white p-5 shadow-sm ${className}`}>{children}</div>;
}

export function PageTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-4 text-xl font-bold">{children}</h2>;
}

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
  const styles: Record<string, string> = {
    primary: "bg-orange text-white",
    secondary: "bg-teal text-white",
    ghost: "bg-gray-100 text-gray-700",
    danger: "bg-red-50 text-red-600",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`w-full rounded-full px-4 py-2 text-sm font-semibold transition active:scale-[0.98] disabled:opacity-50 ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-gray-700">{label}</span>
      {children}
    </label>
  );
}

export const inputCls =
  "w-full rounded-xl border border-gray-200 px-3 py-2 outline-none focus:border-orange focus:ring-2 focus:ring-orange/20";
