import { useState, type ChangeEvent, type FormEvent } from "react";
import { useProducts, useProductMutations } from "../lib/queries";
import { api, ApiError } from "../lib/api";
import { fmtRp } from "../lib/format";
import { Button, Card, ErrorBox, Field, inputCls, PageTitle, Spinner } from "../components/ui";
import type { Product } from "../lib/types";

type ProductInput = { name: string; price: number; description?: string; image_url?: string };

function ProductForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: Product;
  onSubmit: (d: ProductInput) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [price, setPrice] = useState(initial?.price ?? 0);
  const [desc, setDesc] = useState(initial?.description ?? "");
  const [imageUrl, setImageUrl] = useState(initial?.image_url ?? "");
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
      await onSubmit({ name, price, description: desc, image_url: imageUrl || undefined });
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Gagal menyimpan.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-2">
      {err && <ErrorBox message={err} />}
      <Field label="Nama Produk">
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nasi Goreng" />
      </Field>
      <Field label="Harga (Rp)">
        <input className={inputCls} type="number" value={price} onChange={(e) => setPrice(Number(e.target.value))} />
      </Field>
      <Field label="Deskripsi">
        <textarea className={inputCls} value={desc} onChange={(e) => setDesc(e.target.value)} />
      </Field>
      <Field label="Foto (opsional)">
        <input type="file" accept="image/*" onChange={upload} className="text-sm" />
      </Field>
      {imageUrl && <img src={imageUrl} alt="" className="h-20 rounded-lg object-cover" />}
      <div className="grid grid-cols-2 gap-2">
        <Button type="submit" disabled={busy}>{busy ? "..." : "💾 Simpan"}</Button>
        <Button variant="ghost" onClick={onCancel}>Batal</Button>
      </div>
    </form>
  );
}

export default function Catalog() {
  const { data, isLoading, error } = useProducts();
  const { create, update, remove } = useProductMutations();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <PageTitle>🏪 Katalog Produk</PageTitle>
        <button onClick={() => setAdding((a) => !a)} className="rounded-full bg-orange px-3 py-1 text-sm font-semibold text-white">
          ➕ Tambah
        </button>
      </div>

      {adding && (
        <Card className="mb-4">
          <ProductForm
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
      {data && data.length === 0 && !adding && <Card><p className="text-sm text-gray-500">Belum ada produk. 🏪</p></Card>}

      <div className="grid grid-cols-2 gap-3">
        {data?.map((p) => (
          <div key={p.id} className="overflow-hidden rounded-2xl bg-white shadow-sm">
            {p.image_url ? (
              <img src={p.image_url} alt={p.name} className="h-32 w-full object-cover" />
            ) : (
              <div className="flex h-32 w-full items-center justify-center bg-teal-light text-4xl">📦</div>
            )}
            <div className="p-3">
              <p className="font-bold">{p.name}</p>
              <p className="font-bold text-orange">{fmtRp(p.price)}</p>
              <p className="line-clamp-2 text-xs text-gray-500">{p.description || "—"}</p>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button variant="ghost" onClick={() => setEditing(editing === p.id ? null : p.id)}>✏️ Edit</Button>
                <Button variant="danger" onClick={() => remove.mutate(p.id)}>🗑️ Hapus</Button>
              </div>
              {editing === p.id && (
                <div className="mt-2">
                  <ProductForm
                    initial={p}
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
