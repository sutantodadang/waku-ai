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
    <div className="mx-auto min-h-full max-w-[900px] px-4 pb-24 pt-4">
      <header className="mb-4 flex items-center justify-between">
        <div className="font-extrabold text-teal-dark">Waku 🤖</div>
        <div className="flex items-center gap-3 text-sm">
          {businessName && <span className="max-w-[140px] truncate text-gray-500">🏪 {businessName}</span>}
          <button onClick={logout} className="rounded-full bg-gray-100 px-3 py-1 font-semibold text-gray-700">
            Keluar
          </button>
        </div>
      </header>
      <Outlet />
      <BottomNav />
    </div>
  );
}
