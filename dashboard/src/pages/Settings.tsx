import { useEffect, useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { useSettings, useUpdateSettings, useUpdateBusiness, useBusiness, useStaff, useCreateStaff, useDeleteStaff } from "../lib/queries";
import { api, ApiError } from "../lib/api";
import { authStore, useAuth } from "../lib/auth";
import { Button, Card, ErrorBox, Field, inputCls, PageTitle, Spinner } from "../components/ui";
import type { BusinessType, FAQItem, PaymentMethod, Settings as SettingsT } from "../lib/types";
import { toast } from "../lib/toast";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-3 font-display text-base font-bold text-ink">{children}</h2>;
}

export default function Settings() {
  const { data, isLoading, error } = useSettings();
  const save = useUpdateSettings();
  const { businessName } = useAuth();
  const updateBiz = useUpdateBusiness();
  const { data: bizData } = useBusiness();
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [qris, setQris] = useState("");
  const [qrisPayload, setQrisPayload] = useState("");
  const [qrisGenerating, setQrisGenerating] = useState(false);

  const [form, setForm] = useState<SettingsT | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  // Seed payment state from server so saves never wipe existing methods
  useEffect(() => {
    if (bizData) {
      setMethods(bizData.payment_methods ?? []);
      setQris(bizData.qris_image_url ?? "");
    }
  }, [bizData]);

  // Profil bisnis (rename)
  const [bizName, setBizName] = useState("");
  const [bizMsg, setBizMsg] = useState("");
  useEffect(() => {
    setBizName(businessName ?? "");
  }, [businessName]);
  async function renameBiz() {
    try {
      const r = await api.renameBusiness(bizName.trim());
      authStore.setBusinessName(r.business_name);
      setBizMsg("Nama bisnis diperbarui!");
    } catch (x) {
      setBizMsg(x instanceof ApiError ? x.message : "Gagal.");
    }
  }

  // Tipe bisnis
  const [bizType, setBizType] = useState<BusinessType>("warung");
  useEffect(() => {
    if (bizData?.business_type) setBizType(bizData.business_type);
  }, [bizData]);
  function saveBizType() {
    updateBiz.mutate({ business_name: bizName.trim() || (businessName ?? ""), business_type: bizType });
  }

  // Staff (salon only)
  const { data: staffList } = useStaff();
  const createStaff = useCreateStaff();
  const deleteStaff = useDeleteStaff();
  const [newStaffName, setNewStaffName] = useState("");

  async function handleQrisFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const url = await api.upload(file);
      setQris(url);
      toast.success("Gambar QRIS berhasil diupload.");
    } catch (x) {
      toast.error(x instanceof ApiError ? x.message : "Gagal mengupload gambar QRIS.");
    }
  }

  async function handleGenerateQris() {
    const p = qrisPayload.trim();
    if (!p) { toast.error("Masukkan kode QRIS terlebih dahulu."); return; }
    setQrisGenerating(true);
    try {
      const url = await api.generateQris(p);
      setQris(url);
      toast.success("QR QRIS berhasil dibuat.");
    } catch (x) {
      toast.error(x instanceof ApiError ? x.message : "Gagal membuat QR QRIS.");
    } finally {
      setQrisGenerating(false);
    }
  }

  function addMethod() {
    setMethods((m) => [...m, { type: "rekening", label: "", value: "" }]);
  }
  function savePayment() {
    updateBiz.mutate({ business_name: bizName.trim() || (businessName ?? ""), payment_methods: methods, qris_image_url: qris || null });
  }

  function update<K extends keyof SettingsT>(k: K, v: SettingsT[K]) {
    setForm((f) => (f ? { ...f, [k]: v } : f));
  }
  function setFaq(i: number, patch: Partial<FAQItem>) {
    setForm((f) => {
      if (!f) return f;
      const faq = [...f.faq];
      faq[i] = { ...faq[i], ...patch };
      return { ...f, faq };
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaved(false);
    await save.mutateAsync({ ...form, faq: form.faq.filter((q) => q.question && q.answer) });
    setSaved(true);
  }

  return (
    <div className="space-y-4">
      <PageTitle>Auto-Balas</PageTitle>

      <Card>
        <Link to="/whatsapp" className="flex items-center justify-between">
          <span>
            <span className="block font-semibold text-ink">Koneksi WhatsApp</span>
            <span className="block text-sm text-ink/50">Hubungkan / cek status nomor bisnis.</span>
          </span>
          <span className="text-ink/30" aria-hidden>→</span>
        </Link>
      </Card>

      <Card>
        <SectionTitle>Profil bisnis</SectionTitle>
        <Field label="Nama bisnis">
          <input className={inputCls} value={bizName} onChange={(e) => setBizName(e.target.value)} />
        </Field>
        <div className="mt-3">
          <Button onClick={renameBiz} disabled={!bizName.trim()}>Simpan nama</Button>
        </div>
        {bizMsg && <p className="mt-2 text-sm text-brand-deep">{bizMsg}</p>}
      </Card>

      <Card>
        <SectionTitle>Tipe bisnis</SectionTitle>
        <Field label="Tipe">
          <select
            className={inputCls}
            value={bizType}
            onChange={(e) => setBizType(e.target.value as BusinessType)}
          >
            <option value="warung">Warung / Toko</option>
            <option value="salon">Salon / Barbershop</option>
            <option value="wedding">Wedding / Event</option>
          </select>
        </Field>
        <div className="mt-3">
          <Button onClick={saveBizType} disabled={updateBiz.isPending}>
            {updateBiz.isPending ? "..." : "Simpan tipe"}
          </Button>
        </div>
      </Card>

      {bizType === "salon" && (
        <Card>
          <SectionTitle>Manajemen Staff</SectionTitle>
          {staffList && staffList.length === 0 && (
            <p className="mb-3 text-sm text-ink/50">Belum ada staff. Tambah staff pertama.</p>
          )}
          {staffList?.map((s) => (
            <div key={s.id} className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-ink">{s.name}</span>
              <button
                type="button"
                onClick={() => deleteStaff.mutate(s.id)}
                className="text-sm font-medium text-red-600"
              >
                Hapus
              </button>
            </div>
          ))}
          <div className="mt-3 flex gap-2">
            <input
              className={inputCls}
              placeholder="Nama staff"
              value={newStaffName}
              onChange={(e) => setNewStaffName(e.target.value)}
            />
            <Button
              onClick={() => {
                if (!newStaffName.trim()) return;
                createStaff.mutate(newStaffName.trim(), { onSuccess: () => setNewStaffName("") });
              }}
              disabled={createStaff.isPending || !newStaffName.trim()}
            >
              {createStaff.isPending ? "..." : "+ Tambah"}
            </Button>
          </div>
        </Card>
      )}

      <Card>
        <h2 className="mb-1 font-display text-base font-bold text-ink">Metode Pembayaran</h2>
        <p className="mb-3 text-sm text-ink/55">Info ini dikirim otomatis ke pelanggan setelah pesanan selesai.</p>
        {methods.map((m, i) => (
          <div key={i} className="mb-2 flex gap-2">
            <select
              className={inputCls}
              value={m.type}
              onChange={(e) => setMethods((arr) => arr.map((x, j) => (j === i ? { ...x, type: e.target.value as PaymentMethod["type"] } : x)))}
            >
              <option value="rekening">Rekening</option>
              <option value="ewallet">E-wallet</option>
              <option value="qris">QRIS</option>
            </select>
            <input className={inputCls} placeholder="Label (BCA)" value={m.label}
              onChange={(e) => setMethods((arr) => arr.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
            <input className={inputCls} placeholder="Nomor / a.n." value={m.value}
              onChange={(e) => setMethods((arr) => arr.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
            <button type="button" onClick={() => setMethods((arr) => arr.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <Button variant="ghost" type="button" onClick={addMethod}>+ Tambah metode</Button>

        {/* ── QRIS block ── */}
        <div className="mt-4 space-y-3 rounded-xl border border-ink/10 p-4">
          <p className="font-semibold text-ink text-sm">Gambar QRIS (opsional)</p>

          <Field label="URL gambar QRIS">
            <input
              className={inputCls}
              value={qris}
              onChange={(e) => setQris(e.target.value)}
              placeholder="https://..."
            />
          </Field>

          <Field label="Upload gambar QRIS">
            <input
              type="file"
              accept="image/*"
              className="text-sm text-ink/70"
              onChange={handleQrisFile}
            />
          </Field>

          <Field label="Generate dari kode QRIS">
            <textarea
              className={`${inputCls} min-h-[3rem] py-2 font-mono text-xs`}
              value={qrisPayload}
              onChange={(e) => setQrisPayload(e.target.value)}
              placeholder="00020101021126610014COM.GO-JEK.WWW..."
            />
            <Button
              type="button"
              variant="ghost"
              onClick={handleGenerateQris}
              disabled={qrisGenerating}
              className="mt-1"
            >
              {qrisGenerating ? "Membuat..." : "Buat QR"}
            </Button>
          </Field>

          {qris && (
            <img
              src={qris}
              alt="Preview QRIS"
              className="mt-2 h-36 w-36 rounded-lg border border-ink/10 object-contain"
            />
          )}
        </div>

        <Button onClick={savePayment} disabled={updateBiz.isPending}>{updateBiz.isPending ? "..." : "Simpan pembayaran"}</Button>
      </Card>

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {form && (
        <form onSubmit={submit} className="space-y-4">
          <Card>
            <label className="flex items-center justify-between gap-3">
              <span>
                <span className="block font-semibold text-ink">Balas otomatis</span>
                <span className="block text-sm text-ink/50">Waku jawab pelanggan saat kamu sibuk.</span>
              </span>
              <span className="relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={form.auto_reply_enabled}
                  onChange={(e) => update("auto_reply_enabled", e.target.checked)}
                />
                <span className="absolute inset-0 rounded-full bg-ink/15 transition peer-checked:bg-brand" />
                <span className="absolute left-0.5 h-6 w-6 rounded-full bg-white shadow transition peer-checked:translate-x-5" />
              </span>
            </label>
          </Card>

          <Card className="space-y-3">
            <SectionTitle>Pesan</SectionTitle>
            <Field label="Pesan sambutan">
              <textarea
                className={`${inputCls} min-h-[4rem] py-2`}
                value={form.greeting_message}
                onChange={(e) => update("greeting_message", e.target.value)}
                placeholder="Halo! Ada yang bisa Waku bantu?"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Jam buka">
                <input
                  className={inputCls}
                  value={form.business_hours.open}
                  onChange={(e) => update("business_hours", { ...form.business_hours, open: e.target.value })}
                  placeholder="08:00"
                />
              </Field>
              <Field label="Jam tutup">
                <input
                  className={inputCls}
                  value={form.business_hours.close}
                  onChange={(e) => update("business_hours", { ...form.business_hours, close: e.target.value })}
                  placeholder="21:00"
                />
              </Field>
            </div>
            <Field label="Pesan di luar jam kerja">
              <input
                className={inputCls}
                value={form.after_hours_message}
                onChange={(e) => update("after_hours_message", e.target.value)}
              />
            </Field>
          </Card>

          <Card className="space-y-3">
            <div className="flex items-center justify-between">
              <SectionTitle>Pertanyaan umum</SectionTitle>
              <button
                type="button"
                onClick={() => update("faq", [...form.faq, { question: "", answer: "" }])}
                className="-mt-1 min-h-[2rem] rounded-full bg-ink/5 px-3 text-sm font-semibold text-ink/70 transition active:scale-[0.98]"
              >
                + Tambah
              </button>
            </div>
            {form.faq.length === 0 && <p className="text-sm text-ink/50">Belum ada pertanyaan umum.</p>}
            {form.faq.map((q, i) => (
              <div key={i} className="space-y-2 rounded-2xl bg-paper p-3 ring-1 ring-ink/[0.05]">
                <input
                  className={inputCls}
                  value={q.question}
                  onChange={(e) => setFaq(i, { question: e.target.value })}
                  placeholder="Pertanyaan"
                />
                <textarea
                  className={`${inputCls} min-h-[3.5rem] py-2`}
                  value={q.answer}
                  onChange={(e) => setFaq(i, { answer: e.target.value })}
                  placeholder="Jawaban"
                />
                <button
                  type="button"
                  onClick={() => update("faq", form.faq.filter((_, idx) => idx !== i))}
                  className="text-sm font-medium text-red-600"
                >
                  Hapus
                </button>
              </div>
            ))}
          </Card>

          {saved && (
            <div className="rounded-2xl bg-brand-tint p-3 text-sm font-medium text-brand-deep ring-1 ring-brand/15">
              Pengaturan tersimpan.
            </div>
          )}
          <Button type="submit" disabled={save.isPending}>{save.isPending ? "..." : "Simpan pengaturan"}</Button>
        </form>
      )}
    </div>
  );
}
