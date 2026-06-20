import { Link } from "@tanstack/react-router";

const items = [
  { to: "/", icon: "🏠", label: "Beranda" },
  { to: "/orders", icon: "📋", label: "Pesanan" },
  { to: "/catalog", icon: "🏪", label: "Katalog" },
  { to: "/settings", icon: "⚙️", label: "Auto-Balas" },
  { to: "/whatsapp", icon: "📲", label: "Koneksi" },
] as const;

export default function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-1/2 z-50 flex w-full max-w-[900px] -translate-x-1/2 justify-around border-t border-gray-200 bg-white px-2 shadow-[0_-2px_10px_rgba(0,0,0,0.06)]">
      {items.map((it) => (
        <Link
          key={it.to}
          to={it.to}
          activeOptions={{ exact: it.to === "/" }}
          className="flex flex-1 flex-col items-center gap-0.5 py-2"
          activeProps={{ className: "text-orange font-semibold" }}
          inactiveProps={{ className: "text-gray-500" }}
        >
          <span className="text-xl leading-none">{it.icon}</span>
          <span className="text-[0.65rem]">{it.label}</span>
        </Link>
      ))}
    </nav>
  );
}
