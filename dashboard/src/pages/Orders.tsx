import { useState } from "react";
import { useOrders, useUpdateOrderStatus, useSendOrderPayment } from "../lib/queries";
import { fmtRp } from "../lib/format";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBox, PageTitle, Spinner } from "../components/ui";
import type { OrderStatus } from "../lib/types";

const FILTERS: [string, string][] = [
  ["semua", "Semua"],
  ["baru", "Baru"],
  ["diproses", "Diproses"],
  ["selesai", "Selesai"],
  ["dibatalkan", "Dibatalkan"],
];
const LABEL: Record<string, string> = { baru: "Baru", diproses: "Diproses", selesai: "Selesai", dibatalkan: "Dibatalkan" };
const BADGE: Record<string, string> = {
  baru: "bg-blue-50 text-blue-700",
  diproses: "bg-gold/15 text-[#9a7400]",
  selesai: "bg-brand-tint text-brand-deep",
  dibatalkan: "bg-red-50 text-red-600",
};

export default function Orders() {
  const [filter, setFilter] = useState("semua");
  const { data, isLoading, error } = useOrders(filter === "semua" ? undefined : filter);
  const upd = useUpdateOrderStatus();
  const sendPay = useSendOrderPayment();
  const set = (id: string, status: OrderStatus) => upd.mutate({ id, status });

  return (
    <div>
      <PageTitle>Pesanan</PageTitle>

      {/* Horizontal filter chips read better than a dropdown on a phone. */}
      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1 [-ms-overflow-style:none] [scrollbar-width:none]">
        {FILTERS.map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            className={`min-h-[2.25rem] shrink-0 rounded-full px-3.5 text-sm font-semibold transition ${
              filter === v ? "bg-ink text-white" : "bg-white text-ink/55 ring-1 ring-ink/10"
            }`}
          >
            {l}
          </button>
        ))}
      </div>

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {data && data.length === 0 && (
        <Card>
          <p className="text-sm text-ink/55">Belum ada pesanan di sini.</p>
        </Card>
      )}

      <div className="space-y-3">
        {data?.map((o) => (
          <Card key={o.id}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-bold text-ink">{o.customer_name}</p>
                <p className="mt-0.5 text-xs text-ink/45">
                  #{String(o.order_seq).padStart(4, "0")} • {new Date(o.created_at).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${BADGE[o.status] ?? "bg-ink/5 text-ink/60"}`}>
                {LABEL[o.status] ?? o.status}
              </span>
            </div>

            <p className="tnum mt-2 text-xl font-extrabold text-ink">{fmtRp(o.total)}</p>

            {o.items && o.items.length > 0 && (
              <ul className="mt-2 space-y-0.5 border-t border-ink/[0.06] pt-2">
                {o.items.map((it, i) => (
                  <li key={i} className="flex justify-between text-sm text-ink/60">
                    <span className="truncate">
                      {it.name} <span className="text-ink/40">×{it.quantity ?? it.qty ?? 1}</span>
                    </span>
                    <span className="tnum shrink-0 pl-2">{fmtRp(it.price ?? 0)}</span>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              {(o.status === "baru" || o.status === "diproses") && (
                <>
                  {o.status === "baru" && (
                    <Button variant="secondary" onClick={() => set(o.id, "diproses")}>Proses</Button>
                  )}
                  <Button onClick={() => set(o.id, "selesai")}>Selesai</Button>
                  <Button variant="danger" onClick={() => set(o.id, "dibatalkan")}>Batal</Button>
                </>
              )}
              <Button variant="ghost" onClick={() => sendPay.mutate(o.id)} disabled={sendPay.isPending}>
                {sendPay.isPending ? "..." : "Kirim info bayar"}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
