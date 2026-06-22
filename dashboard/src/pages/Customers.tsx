import { useState } from "react";
import { useCustomers, useCustomer, useUpdateCustomer } from "../lib/queries";
import { fmtRp } from "../lib/format";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBox, PageTitle, Spinner, inputCls } from "../components/ui";
import type { Customer } from "../lib/types";

function rel(iso: string | null): string {
  if (!iso) return "belum pernah order";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "hari ini";
  if (days === 1) return "kemarin";
  return `${days} hari lalu`;
}

function Detail({ id, onBack }: { id: number; onBack: () => void }) {
  const { data, isLoading, error } = useCustomer(id);
  const upd = useUpdateCustomer(id);
  const [notes, setNotes] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState("");

  if (error) return <ErrorBox message={(error as ApiError).message} />;
  if (isLoading || !data) return <Spinner />;
  const notesVal = notes ?? data.notes ?? "";
  const tags = data.tags ?? [];

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm font-semibold text-ink/55">← Kembali</button>

      <section className="rounded-[24px] bg-ink p-5 text-white shadow-[0_8px_24px_rgba(12,31,23,0.18)]">
        <div className="flex items-center justify-between">
          <p className="font-display text-xl font-extrabold">{data.name ?? data.phone_number}</p>
          {data.is_regular && <span className="rounded-full bg-gold/20 px-2.5 py-1 text-xs font-bold text-gold">Langganan</span>}
        </div>
        <p className="mt-1 text-sm text-white/55">{data.order_count} order • {rel(data.last_order_at)}</p>
        <p className="tnum mt-3 font-display text-3xl font-extrabold text-gold">{fmtRp(data.total_spent)}</p>
        <p className="text-xs text-white/55">total belanja</p>
      </section>

      {data.top_items.length > 0 && (
        <Card>
          <h2 className="mb-2 font-display text-base font-bold text-ink">Item favorit</h2>
          <div className="flex flex-wrap gap-2">
            {data.top_items.map((t) => (
              <span key={t.name + t.count} className="rounded-full bg-brand-tint px-3 py-1 text-sm font-semibold text-brand-deep">
                {t.name} · {t.count}×
              </span>
            ))}
          </div>
        </Card>
      )}

      <Card className="space-y-3">
        <h2 className="font-display text-base font-bold text-ink">Catatan & preferensi</h2>
        <textarea
          className={`${inputCls} min-h-[4rem] py-2`}
          value={notesVal}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="mis. tanpa pedas, alamat antar, alergi udang"
        />
        <div className="flex flex-wrap gap-2">
          {tags.map((tg) => (
            <span key={tg} className="flex items-center gap-1 rounded-full bg-ink/5 px-3 py-1 text-sm text-ink/70">
              {tg}
              <button onClick={() => upd.mutate({ tags: tags.filter((x) => x !== tg) })} className="text-ink/40">×</button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input className={inputCls} value={tagInput} onChange={(e) => setTagInput(e.target.value)} placeholder="Tambah tag" />
          <Button
            variant="ghost"
            onClick={() => {
              const tg = tagInput.trim();
              if (tg && !tags.includes(tg)) upd.mutate({ tags: [...tags, tg] });
              setTagInput("");
            }}
          >
            Tambah
          </Button>
        </div>
        <label className="flex items-center justify-between">
          <span className="font-semibold text-ink">Tandai langganan</span>
          <input
            type="checkbox"
            className="h-5 w-9 accent-brand"
            checked={data.is_regular_override ?? data.is_regular}
            onChange={(e) => upd.mutate({ is_regular_override: e.target.checked })}
          />
        </label>
        <Button onClick={() => upd.mutate({ notes: notesVal })} disabled={upd.isPending}>
          {upd.isPending ? "..." : "Simpan catatan"}
        </Button>
      </Card>
    </div>
  );
}

export default function Customers() {
  const { data, isLoading, error } = useCustomers();
  const [openId, setOpenId] = useState<number | null>(null);

  if (openId !== null) return <Detail id={openId} onBack={() => setOpenId(null)} />;

  return (
    <div>
      <PageTitle>Pelanggan</PageTitle>
      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {data && data.length === 0 && (
        <Card><p className="text-sm text-ink/55">Belum ada pelanggan. Mereka muncul di sini setelah chat pertama.</p></Card>
      )}
      <div className="space-y-2">
        {data?.map((c: Customer) => (
          <button key={c.id} onClick={() => setOpenId(c.id)} className="w-full text-left">
            <Card className="flex items-center justify-between !p-4">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <span className="truncate">{c.name ?? c.phone_number}</span>
                  {c.is_regular && <span className="shrink-0 rounded-full bg-gold/15 px-2 py-0.5 text-[0.65rem] font-bold text-[#9a7400]">Langganan</span>}
                </p>
                <p className="mt-0.5 text-xs text-ink/45">{c.order_count} order • {rel(c.last_order_at)}</p>
              </div>
              <span className="tnum shrink-0 pl-2 font-bold text-ink">{fmtRp(c.total_spent)}</span>
            </Card>
          </button>
        ))}
      </div>
    </div>
  );
}
