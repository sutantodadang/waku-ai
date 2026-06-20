import { useState, type FormEvent } from "react";
import { useWhatsapp, useConnectWhatsapp } from "../lib/queries";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBox, Field, inputCls, PageTitle, Spinner } from "../components/ui";

export default function Whatsapp() {
  const { data, isLoading, error } = useWhatsapp();
  const connect = useConnectWhatsapp();
  const [pnid, setPnid] = useState("");
  const [token, setToken] = useState("");
  const [waba, setWaba] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(false);
    if (!pnid || !token) {
      setErr("Phone Number ID dan Access Token wajib diisi.");
      return;
    }
    try {
      await connect.mutateAsync({ phone_number_id: pnid, access_token: token, waba_id: waba || undefined });
      setErr("");
      setOk(true);
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Gagal menghubungkan.");
    }
  }

  return (
    <div>
      <PageTitle>📲 Koneksi WhatsApp</PageTitle>
      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {data &&
        (data.is_connected ? (
          <Card className="mb-4">
            <div className="rounded-xl bg-green-50 p-3 text-sm text-green-700">
              ✅ Terhubung — phone_number_id: {data.phone_number_id}
            </div>
          </Card>
        ) : (
          <Card className="mb-4">
            <div className="rounded-xl bg-yellow-50 p-3 text-sm text-yellow-800">
              ⚠️ Belum terhubung. Nomor WhatsApp bisnis belum bisa membalas pelanggan.
            </div>
          </Card>
        ))}

      <Card>
        <p className="mb-3 text-sm text-gray-500">
          Nanti via <b>Embedded Signup</b> Meta (sekali klik) setelah akun lolos App Review. Untuk sekarang (test),
          masukkan kredensial Cloud API manual:
        </p>
        <form onSubmit={submit} className="space-y-3">
          {err && <ErrorBox message={err} />}
          {ok && <div className="rounded-xl bg-green-50 p-3 text-sm text-green-700">✅ WhatsApp berhasil dihubungkan!</div>}
          <Field label="Phone Number ID">
            <input className={inputCls} value={pnid} onChange={(e) => setPnid(e.target.value)} placeholder="dari Meta API Setup" />
          </Field>
          <Field label="Access Token">
            <input className={inputCls} type="password" value={token} onChange={(e) => setToken(e.target.value)} />
          </Field>
          <Field label="WABA ID (opsional)">
            <input className={inputCls} value={waba} onChange={(e) => setWaba(e.target.value)} />
          </Field>
          <Button type="submit" disabled={connect.isPending}>{connect.isPending ? "..." : "🔗 Hubungkan"}</Button>
        </form>
      </Card>
    </div>
  );
}
