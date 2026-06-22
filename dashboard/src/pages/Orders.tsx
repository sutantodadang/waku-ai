import { useState } from "react";
import { useOrders, useUpdateOrderStatus } from "../lib/queries";
import { fmtRp } from "../lib/format";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBox, inputCls, PageTitle, Spinner } from "../components/ui";
import type { OrderStatus } from "../lib/types";

const FILTERS: [string, string][] = [
  ["semua", "Semua Pesanan"],
  ["baru", "🆕 Baru"],
  ["diproses", "🔄 Diproses"],
  ["selesai", "✅ Selesai"],
  ["dibatalkan", "❌ Dibatalkan"],
];
const LABEL: Record<string, string> = { baru: "🆕 Baru", diproses: "🔄 Diproses", selesai: "✅ Selesai", dibatalkan: "❌ Dibatalkan" };
const BADGE: Record<string, string> = {
  baru: "bg-blue-100 text-blue-700",
  diproses: "bg-orange-100 text-orange-700",
  selesai: "bg-green-100 text-green-700",
  dibatalkan: "bg-red-100 text-red-700",
};

export default function Orders() {
  const [filter, setFilter] = useState("semua");
  const { data, isLoading, error } = useOrders(filter === "semua" ? undefined : filter);
  const upd = useUpdateOrderStatus();
  const set = (id: number, status: OrderStatus) => upd.mutate({ id, status });

  return (
    <div>
      <PageTitle>📋 Daftar Pesanan</PageTitle>
      <select value={filter} onChange={(e) => setFilter(e.target.value)} className={`${inputCls} mb-4`}>
        {FILTERS.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {data && data.length === 0 && <Card><p className="text-sm text-gray-500">Belum ada pesanan. 😊</p></Card>}

      {data?.map((o) => (
        <Card key={o.id} className="mb-3">
          <div className="flex items-center justify-between">
            <strong>{o.customer_name}</strong>
            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${BADGE[o.status] ?? "bg-gray-100"}`}>
              {LABEL[o.status] ?? o.status}
            </span>
          </div>
          <p className="my-1 text-xs text-gray-500">Pesanan #{o.id} • {new Date(o.created_at).toLocaleString("id-ID")}</p>
          <p className="tnum text-lg font-extrabold text-ink">{fmtRp(o.total)}</p>
          {o.items?.map((it, i) => (
            <p key={i} className="ml-3 text-sm text-gray-600">
              • {it.name} x{it.quantity ?? it.qty ?? 1} — {fmtRp(it.price ?? 0)}
            </p>
          ))}
          {(o.status === "baru" || o.status === "diproses") && (
            <div className="mt-3 grid grid-cols-3 gap-2">
              {o.status === "baru" ? (
                <Button variant="secondary" onClick={() => set(o.id, "diproses")}>🔄 Proses</Button>
              ) : (
                <span />
              )}
              <Button onClick={() => set(o.id, "selesai")}>✅ Selesai</Button>
              <Button variant="danger" onClick={() => set(o.id, "dibatalkan")}>❌ Batal</Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
