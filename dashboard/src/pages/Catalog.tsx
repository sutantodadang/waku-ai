import { useState, type ChangeEvent, type FormEvent } from "react";
import { useProducts, useProductMutations, useBusiness } from "../lib/queries";
import { api, ApiError } from "../lib/api";
import { fmtRp } from "../lib/format";
import { Button, Card, ErrorBox, Field, inputCls, PageTitle, Spinner } from "../components/ui";
import type { Product } from "../lib/types";

type ProductInput = { name: string; price: number; description?: string; image_url?: string; duration_minutes?: number | null };

function ProductForm({
  initial,
  onSubmit,
  onCancel,
  isSalon,
}: {
  initial?: Product;
  onSubmit: (d: ProductInput) => Promise<void>;
  onCancel: () => void;
  isSalon?: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [price, setPrice] = useState(initial?.price ?? 0);
  const [desc, setDesc] = useState(initial?.description ?? "");
  const [imageUrl, setImageUrl] = useState(initial?.image_url ?? "");
  const [durationMinutes, setDurationMinutes] = useState<number | "">(initial?.duration_minutes ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      setImageUrl(await api.upload(f));
    } catch {
      setErr("Upload gambar gagal.");
    }
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name || price <= 0) {
      setErr("Nama dan harga wajib diisi.");
      return;
    }
    setBusy(true);
    try {
      await onSubmit({
        name,
        price,
        description: desc,
        image_url: imageUrl || undefined,
        duration_minutes: isSalon && durationMinutes !== "" ? Number(durationMinutes) : null,
      });
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Gagal menyimpan.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      {err && <ErrorBox message={err} />}
      <Field label="Nama produk">
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nasi Goreng" />
      </Field>
      <Field label="Harga (Rp)">
        <input className={inputCls} type="number" inputMode="numeric" value={price} onChange={(e) => setPrice(Number(e.target.value))} />
      </Field>
      {isSalon && (
        <Field label="Durasi (menit)">
          <input
            className={inputCls}
            type="number"
            inputMode="numeric"
            value={durationMinutes}
            onChange={(e) => setDurationMinutes(e.target.value === "" ? "" : Number(e.target.value))}
            placeholder="60"
          />
        </Field>
      )}
      <Field label="Deskripsi">
        <textarea className={`${inputCls} min-h-[4rem] py-2`} value={desc} onChange={(e) => setDesc(e.target.value)} />
      </Field>
      <Field label="Foto (opsional)">
        <input type="file" accept="image/*" onChange={upload} className="text-sm text-ink/60 file:mr-2 file:rounded-full file:border-0 file:bg-brand-tint file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-brand-deep" />
      </Field>
      {imageUrl && <img src={imageUrl} alt="" className="h-24 w-full rounded-xl object-cover" />}
      <div className="grid grid-cols-2 gap-2">
        <Button type="submit" disabled={busy}>{busy ? "..." : "Simpan"}</Button>
        <Button variant="ghost" onClick={onCancel}>Batal</Button>
      </div>
    </form>
  );
}

export default function Catalog() {
  const { data, isLoading, error } = useProducts();
  const { create, update, remove } = useProductMutations();
  const { data: bizData } = useBusiness();
  const isSalon = bizData?.business_type === "salon";
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <PageTitle>Katalog</PageTitle>
        <button
          onClick={() => setAdding((a) => !a)}
          className="min-h-[2.25rem] shrink-0 rounded-full bg-accent px-4 text-sm font-semibold text-white shadow-[0_2px_10px_rgba(255,90,54,0.28)] transition active:scale-[0.98]"
        >
          {adding ? "Tutup" : "+ Tambah"}
        </button>
      </div>

      {adding && (
        <Card className="mb-4">
          <ProductForm
            isSalon={isSalon}
            onSubmit={async (d) => {
              await create.mutateAsync(d);
              setAdding(false);
            }}
            onCancel={() => setAdding(false)}
          />
        </Card>
      )}

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {data && data.length === 0 && !adding && (
        <Card>
          <p className="text-sm text-ink/55">Belum ada produk. Tambah menu pertamamu agar Waku bisa menawarkannya ke pelanggan.</p>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3">
        {data?.map((p) => (
          <div key={p.id} className="overflow-hidden rounded-[20px] bg-white ring-1 ring-ink/[0.06] shadow-[0_1px_3px_rgba(12,31,23,0.05)]">
            {p.image_url ? (
              <img src={p.image_url} alt={p.name} className="aspect-square w-full object-cover" />
            ) : (
              <div className="grid aspect-square w-full place-items-center bg-brand-tint text-3xl">🍽️</div>
            )}
            <div className="p-3">
              <p className="truncate font-semibold text-ink">{p.name}</p>
              <p className="tnum mt-0.5 font-bold text-ink">{fmtRp(p.price)}</p>
              {p.description && <p className="mt-1 line-clamp-2 text-xs text-ink/45">{p.description}</p>}
              <div className="mt-2.5 grid grid-cols-2 gap-2">
                <Button variant="ghost" onClick={() => setEditing(editing === p.id ? null : p.id)}>Edit</Button>
                <Button variant="danger" onClick={() => remove.mutate(p.id)}>Hapus</Button>
              </div>
              {editing === p.id && (
                <div className="mt-3">
                  <ProductForm
                    initial={p}
                    isSalon={isSalon}
                    onSubmit={async (d) => {
                      await update.mutateAsync({ id: p.id, data: d });
                      setEditing(null);
                    }}
                    onCancel={() => setEditing(null)}
                  />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
