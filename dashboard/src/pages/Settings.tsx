import { useEffect, useState, type FormEvent } from "react";
import { useSettings, useUpdateSettings } from "../lib/queries";
import { api, ApiError } from "../lib/api";
import { authStore, useAuth } from "../lib/auth";
import { Button, Card, ErrorBox, Field, inputCls, PageTitle, Spinner } from "../components/ui";
import type { FAQItem, Settings as SettingsT } from "../lib/types";

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
    <div>
      <PageTitle>⚙️ Pengaturan Auto-Balas</PageTitle>

      <Card className="mb-4">
        <h3 className="mb-2 font-bold">🏪 Profil Bisnis</h3>
        <Field label="Nama Bisnis">
          <input className={inputCls} value={bizName} onChange={(e) => setBizName(e.target.value)} />
        </Field>
        <div className="mt-2">
          <Button onClick={renameBiz} disabled={!bizName.trim()}>💾 Simpan Nama</Button>
        </div>
        {bizMsg && <p className="mt-2 text-sm text-gray-600">{bizMsg}</p>}
      </Card>

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {form && (
        <form onSubmit={submit} className="space-y-3">
          <Card>
            <label className="flex items-center justify-between">
              <span className="font-semibold">🤖 Aktifkan Auto-Balas</span>
              <input
                type="checkbox"
                className="h-5 w-9 accent-orange"
                checked={form.auto_reply_enabled}
                onChange={(e) => update("auto_reply_enabled", e.target.checked)}
              />
            </label>
          </Card>

          <Card className="space-y-3">
            <Field label="💬 Pesan Sambutan">
              <textarea
                className={inputCls}
                value={form.greeting_message}
                onChange={(e) => update("greeting_message", e.target.value)}
                placeholder="Halo! Ada yang bisa Waku bantu?"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="🕐 Buka">
                <input
                  className={inputCls}
                  value={form.business_hours.open}
                  onChange={(e) => update("business_hours", { ...form.business_hours, open: e.target.value })}
                  placeholder="08:00"
                />
              </Field>
              <Field label="🕐 Tutup">
                <input
                  className={inputCls}
                  value={form.business_hours.close}
                  onChange={(e) => update("business_hours", { ...form.business_hours, close: e.target.value })}
                  placeholder="21:00"
                />
              </Field>
            </div>
            <Field label="🌙 Pesan di Luar Jam Kerja">
              <input
                className={inputCls}
                value={form.after_hours_message}
                onChange={(e) => update("after_hours_message", e.target.value)}
              />
            </Field>
          </Card>

          <Card className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-bold">❓ Pertanyaan Umum (FAQ)</h3>
              <button
                type="button"
                onClick={() => update("faq", [...form.faq, { question: "", answer: "" }])}
                className="rounded-full bg-gray-100 px-3 py-1 text-sm font-semibold"
              >
                ➕ Tambah
              </button>
            </div>
            {form.faq.length === 0 && <p className="text-sm text-gray-500">Belum ada FAQ.</p>}
            {form.faq.map((q, i) => (
              <div key={i} className="space-y-2 rounded-xl bg-gray-50 p-3">
                <input
                  className={inputCls}
                  value={q.question}
                  onChange={(e) => setFaq(i, { question: e.target.value })}
                  placeholder="Pertanyaan"
                />
                <textarea
                  className={inputCls}
                  value={q.answer}
                  onChange={(e) => setFaq(i, { answer: e.target.value })}
                  placeholder="Jawaban"
                />
                <button
                  type="button"
                  onClick={() => update("faq", form.faq.filter((_, idx) => idx !== i))}
                  className="text-sm text-red-600"
                >
                  Hapus
                </button>
              </div>
            ))}
          </Card>

          {saved && <div className="rounded-xl bg-green-50 p-3 text-sm text-green-700">✅ Pengaturan disimpan!</div>}
          <Button type="submit" disabled={save.isPending}>{save.isPending ? "..." : "💾 Simpan Pengaturan"}</Button>
        </form>
      )}
    </div>
  );
}
