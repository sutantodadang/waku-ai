import { useEffect, useState, type FormEvent } from "react";
import { useWhatsapp, useConnectWhatsapp, useEmbeddedSignup } from "../lib/queries";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBox, Field, inputCls, PageTitle, Spinner } from "../components/ui";

const META_APP_ID = import.meta.env.VITE_META_APP_ID as string | undefined;
const META_CONFIG_ID = import.meta.env.VITE_META_CONFIG_ID as string | undefined;
// keep default in sync with backend services/whatsapp.py API_VERSION
const GRAPH_VERSION = (import.meta.env.VITE_META_GRAPH_VERSION as string | undefined) ?? "v23.0";

declare global {
  interface Window {
    FB?: any;
    __waku_fb_init?: () => void;
  }
}

export default function Whatsapp() {
  const { data, isLoading, error } = useWhatsapp();
  const connect = useConnectWhatsapp();
  const signup = useEmbeddedSignup();
  const [pnid, setPnid] = useState("");
  const [token, setToken] = useState("");
  const [waba, setWaba] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);
  const [sdkReady, setSdkReady] = useState(false);

  useEffect(() => {
    if (!META_APP_ID) return;
    const init = () => {
      if (!window.FB) return;
      window.FB.init({ appId: META_APP_ID, autoLogAppEvents: true, xfbml: false, version: GRAPH_VERSION });
      setSdkReady(true);
    };
    window.__waku_fb_init = init;
    if (window.FB) init();
  }, []);

  async function launchEmbeddedSignup() {
    setErr("");
    setOk(false);
    if (!window.FB || !META_CONFIG_ID) {
      setErr("Embedded Signup belum dikonfigurasi (VITE_META_APP_ID / VITE_META_CONFIG_ID).");
      return;
    }
    let captured: { phone_number_id?: string; waba_id?: string } = {};
    // Exact-match allowlist — endsWith("facebook.com") would accept https://evil-facebook.com.
    const ALLOWED_ORIGINS = new Set([
      "https://www.facebook.com",
      "https://web.facebook.com",
      "https://business.facebook.com",
    ]);
    const onMessage = (ev: MessageEvent) => {
      if (!ALLOWED_ORIGINS.has(ev.origin)) return;
      try {
        const d = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data;
        if (d?.type === "WA_EMBEDDED_SIGNUP" && d?.event === "FINISH") {
          captured = { phone_number_id: d.data?.phone_number_id, waba_id: d.data?.waba_id };
        }
      } catch {
        /* ignore non-JSON */
      }
    };
    window.addEventListener("message", onMessage);

    window.FB.login(
      // FB.login rejects an async callback ("Expression is of type asyncfunction,
      // not function"), so keep this sync and run the await work separately.
      (resp: any) => {
        window.removeEventListener("message", onMessage);
        const code = resp?.authResponse?.code;
        if (!code) {
          setErr("Login Meta dibatalkan atau gagal.");
          return;
        }
        if (!captured.phone_number_id || !captured.waba_id) {
          setErr("Tidak menerima data nomor dari Meta. Coba ulangi.");
          return;
        }
        signup
          .mutateAsync({ code, phone_number_id: captured.phone_number_id, waba_id: captured.waba_id })
          .then(() => setOk(true))
          .catch((x) => setErr(x instanceof ApiError ? x.message : "Gagal menyelesaikan Embedded Signup."));
      },
      {
        config_id: META_CONFIG_ID,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {}, featureType: "", sessionInfoVersion: "3" },
      },
    );
  }

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

      <Card className="mb-4">
        <p className="mb-3 text-sm text-gray-500">
          Cara cepat: hubungkan nomor WhatsApp bisnis Anda lewat <b>Embedded Signup</b> Meta (sekali klik).
        </p>
        {err && <ErrorBox message={err} />}
        {ok && <div className="mb-3 rounded-xl bg-green-50 p-3 text-sm text-green-700">✅ WhatsApp berhasil dihubungkan!</div>}
        <Button onClick={launchEmbeddedSignup} disabled={!META_APP_ID || signup.isPending}>
          {signup.isPending ? "..." : "🟢 Hubungkan via Meta"}
        </Button>
        {!META_APP_ID && (
          <p className="mt-2 text-xs text-gray-400">Set VITE_META_APP_ID & VITE_META_CONFIG_ID untuk mengaktifkan.</p>
        )}
        {META_APP_ID && !sdkReady && <p className="mt-2 text-xs text-gray-400">Memuat SDK Meta…</p>}
      </Card>

      <Card>
        <p className="mb-3 text-sm text-gray-500">
          Alternatif (manual / test): masukkan kredensial Cloud API.
        </p>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Phone Number ID">
            <input className={inputCls} value={pnid} onChange={(e) => setPnid(e.target.value)} placeholder="dari Meta API Setup" />
          </Field>
          <Field label="Access Token">
            <input className={inputCls} type="password" value={token} onChange={(e) => setToken(e.target.value)} />
          </Field>
          <Field label="WABA ID (opsional)">
            <input className={inputCls} value={waba} onChange={(e) => setWaba(e.target.value)} />
          </Field>
          <Button type="submit" disabled={connect.isPending}>{connect.isPending ? "..." : "🔗 Hubungkan Manual"}</Button>
        </form>
      </Card>
    </div>
  );
}
