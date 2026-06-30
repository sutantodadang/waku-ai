import { useState } from "react";
import { PageTitle, Card, Button, inputCls } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { toast } from "../lib/toast";

const STEPS = [
  { title: "Hubungkan WhatsApp", body: "Buka menu Auto-Balas → sambungkan nomor WhatsApp bisnis kamu." },
  { title: "Isi Katalog", body: "Tambahkan produk & harga di menu Katalog supaya AI bisa balas pertanyaan harga." },
  { title: "Atur Auto-Balas", body: "Nyalakan balasan otomatis, atur sapaan & jam buka di Pengaturan." },
  { title: "Pantau Pesanan", body: "Pesanan masuk dari chat muncul otomatis di menu Pesanan. Ubah status: Baru → Diproses → Selesai." },
  { title: "Kenali Pelanggan", body: "Lihat riwayat & catatan pelanggan di menu Pelanggan." },
  { title: "Unduh Laporan", body: "Pilih bulan, lalu unduh laporan penjualan dalam format Excel di bawah." },
];

export default function Panduan() {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [loading, setLoading] = useState(false);

  async function handleDownload() {
    setLoading(true);
    try {
      const { blob, filename } = await api.downloadSalesReport(month);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error((e as ApiError).message || "Gagal mengunduh laporan.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageTitle>Panduan</PageTitle>
      <p className="text-sm text-ink/55">Langkah cepat memakai Waku untuk warung & bisnis kamu.</p>

      <Card className="!p-2">
        <ol>
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-3 px-2 py-3 not-last:border-b not-last:border-ink/[0.06]">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-ink/5 text-sm font-bold text-ink/50">
                {i + 1}
              </span>
              <div>
                <p className="font-semibold text-ink">{s.title}</p>
                <p className="mt-0.5 text-sm text-ink/55">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <section>
        <h2 className="mb-2 font-display text-base font-bold text-ink">Laporan Penjualan Bulanan</h2>
        <Card className="space-y-3">
          <input
            type="month"
            className={inputCls}
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <Button onClick={handleDownload} disabled={loading}>
            {loading ? "Menyiapkan…" : "Unduh Excel 📥"}
          </Button>
        </Card>
      </section>
    </div>
  );
}
