import { Link } from "@tanstack/react-router";

const items = [
  { to: "/", icon: "🏠", label: "Beranda" },
  { to: "/orders", icon: "🧾", label: "Pesanan" },
  { to: "/customers", icon: "👥", label: "Pelanggan" },
  { to: "/catalog", icon: "🏪", label: "Katalog" },
  { to: "/settings", icon: "💬", label: "Auto-Balas" },
] as const;

export default function BottomNav() {
  return (
    <nav className="pb-safe fixed bottom-0 left-1/2 z-50 w-full max-w-[640px] -translate-x-1/2 border-t border-ink/[0.06] bg-white/90 px-2 pt-1.5 backdrop-blur-md">
      <div className="flex justify-around">
        {items.map((it) => (
          <Link
            key={it.to}
            to={it.to}
            activeOptions={{ exact: it.to === "/" }}
            className="flex flex-1 flex-col items-center gap-0.5 rounded-2xl py-1.5 transition"
            activeProps={{ className: "text-brand-deep" }}
            inactiveProps={{ className: "text-ink/45" }}
          >
            {({ isActive }) => (
              <>
                <span
                  className={`grid h-8 w-12 place-items-center rounded-full text-lg leading-none transition ${
                    isActive ? "bg-brand-tint" : "bg-transparent"
                  }`}
                >
                  {it.icon}
                </span>
                <span className={`text-[0.68rem] ${isActive ? "font-bold" : "font-medium"}`}>{it.label}</span>
              </>
            )}
          </Link>
        ))}
      </div>
    </nav>
  );
}
