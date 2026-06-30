import { Link } from "@tanstack/react-router";
import { useBusiness } from "../lib/queries";

type NavItem = { to: string; icon: string; label: string };

const WARUNG_ITEMS: NavItem[] = [
  { to: "/", icon: "🏠", label: "Beranda" },
  { to: "/orders", icon: "🧾", label: "Pesanan" },
  { to: "/customers", icon: "👥", label: "Pelanggan" },
  { to: "/catalog", icon: "🏪", label: "Katalog" },
  { to: "/settings", icon: "💬", label: "Auto-Balas" },
  { to: "/panduan", icon: "📖", label: "Panduan" },
];

const BOOKING_ITEMS: NavItem[] = [
  { to: "/", icon: "🏠", label: "Beranda" },
  { to: "/bookings", icon: "📅", label: "Booking" },
  { to: "/customers", icon: "👥", label: "Pelanggan" },
  { to: "/catalog", icon: "🏪", label: "Katalog" },
  { to: "/settings", icon: "💬", label: "Auto-Balas" },
  { to: "/panduan", icon: "📖", label: "Panduan" },
];

export default function BottomNav() {
  const { data: biz } = useBusiness();
  const isBookingBusiness = biz?.business_type === "salon" || biz?.business_type === "wedding";
  const items = isBookingBusiness ? BOOKING_ITEMS : WARUNG_ITEMS;

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
