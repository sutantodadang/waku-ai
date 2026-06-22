import { useEffect, useState, type FormEvent } from "react";
import { useSettings, useUpdateSettings } from "../lib/queries";
import { api, ApiError } from "../lib/api";
import { authStore, useAuth } from "../lib/auth";
import { Button, Card, ErrorBox, Field, inputCls, PageTitle, Spinner } from "../components/ui";
import type { FAQItem, Settings as SettingsT } from "../lib/types";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-3 font-display text-base font-bold text-ink">{children}</h2>;
}

export default function Settings() {
  const { data, isLoading, error } = useSettings();
  const save = useUpdateSettings();
  const { businessName } = useAuth();

  const [form, setForm] = useState<SettingsT | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

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
        <SectionTitle>Profil bisnis</SectionTitle>
        <Field label="Nama bisnis">
          <input className={inputCls} value={bizName} onChange={(e) => setBizName(e.target.value)} />
        </Field>
        <div className="mt-3">
          <Button onClick={renameBiz} disabled={!bizName.trim()}>Simpan nama</Button>
        </div>
        {bizMsg && <p className="mt-2 text-sm text-brand-deep">{bizMsg}</p>}
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
