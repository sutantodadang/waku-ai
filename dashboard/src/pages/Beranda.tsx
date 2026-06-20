import { Link } from "@tanstack/react-router";
import { useSummary } from "../lib/queries";
import { fmtRp, greeting } from "../lib/format";
import { Card, ErrorBox, Spinner } from "../components/ui";
import { ApiError } from "../lib/api";

function Stat({ color, value, label }: { color: string; value: string; label: string }) {
  return (
    <div className={`rounded-2xl p-4 text-white shadow-sm ${color}`}>
      <p className="text-2xl font-extrabold leading-tight">{value}</p>
      <p className="text-sm opacity-90">{label}</p>
    </div>
  );
}

export default function Beranda() {
  const { data, isLoading, error } = useSummary();
  return (
    <div>
      <div className="mb-2 text-center">
        <div className="text-lg font-extrabold">Selamat Datang di Waku 🤖</div>
        <div className="text-sm text-gray-500">Asisten WhatsApp pintar untuk usaha Anda</div>
      </div>
      <h3 className="mb-3 text-lg font-bold">{greeting()}</h3>

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Stat color="bg-gradient-to-br from-teal to-teal-dark" value={String(data.orders_today)} label="📦 Pesanan Hari Ini" />
            <Stat color="bg-gradient-to-br from-orange to-orange-bg" value={fmtRp(data.revenue_today)} label="💰 Pendapatan" />
            <Stat color="bg-gradient-to-br from-green-600 to-green-800" value={String(data.messages_handled)} label="💬 Dibalas Otomatis" />
            <Stat color={data.pending_orders > 0 ? "bg-red-600" : "bg-teal"} value={String(data.pending_orders)} label="⏳ Menunggu" />
          </div>

          <h3 className="my-3 text-lg font-bold">🏆 Produk Terlaris Hari Ini</h3>
          {data.top_products.length === 0 ? (
            <Card><p className="text-sm text-gray-500">Belum ada data penjualan hari ini. 🛍️</p></Card>
          ) : (
            data.top_products.map((p) => (
              <Card key={p.name} className="mb-2 flex items-center justify-between">
                <span className="font-semibold">{p.name}</span>
                <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">{p.count} terjual</span>
              </Card>
            ))
          )}

          <h3 className="my-3 text-lg font-bold">⚡ Aksi Cepat</h3>
          <div className="grid grid-cols-2 gap-3">
            <Link to="/orders" className="rounded-full bg-gray-100 py-2 text-center text-sm font-semibold text-gray-700">📋 Lihat Pesanan</Link>
            <Link to="/catalog" className="rounded-full bg-gray-100 py-2 text-center text-sm font-semibold text-gray-700">🏪 Atur Katalog</Link>
          </div>
        </>
      )}
    </div>
  );
}
