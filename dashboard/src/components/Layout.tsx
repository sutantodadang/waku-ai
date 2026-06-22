import { Outlet } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { authStore, useAuth } from "../lib/auth";
import BottomNav from "./BottomNav";

export default function Layout() {
  const qc = useQueryClient();
  const { businessName } = useAuth();

  function logout() {
    qc.clear();
    authStore.clear();
  }

  return (
    <div className="mx-auto min-h-full max-w-[640px]">
      <header className="pt-safe sticky top-0 z-40 border-b border-ink/[0.06] bg-paper/85 backdrop-blur-md">
        <div className="flex items-center justify-between px-4 pb-3">
          <div className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand text-sm text-white shadow-[0_2px_8px_rgba(0,168,132,0.3)]">
              W
            </span>
            <span className="font-display text-lg font-extrabold tracking-tight text-ink">Waku</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            {businessName && (
              <span className="max-w-[150px] truncate rounded-full bg-white px-3 py-1 font-medium text-ink/70 ring-1 ring-ink/[0.06]">
                {businessName}
              </span>
            )}
            <button
              onClick={logout}
              className="rounded-full px-2.5 py-1 font-semibold text-ink/45 transition hover:text-accent"
            >
              Keluar
            </button>
          </div>
        </div>
      </header>

      <main className="px-4 pb-28 pt-4">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
