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
    <div className="space-y-4">
      <PageTitle>Koneksi WhatsApp</PageTitle>
      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}

      {data && (
        <div
          className={`flex items-center gap-3 rounded-2xl p-4 ring-1 ${
            data.is_connected ? "bg-brand-tint ring-brand/15" : "bg-gold/10 ring-gold/25"
          }`}
        >
          <span
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-bold ${
              data.is_connected ? "bg-brand text-white" : "bg-gold/25 text-[#9a7400]"
            }`}
            aria-hidden
          >
            {data.is_connected ? "✓" : "!"}
          </span>
          <div className="min-w-0 text-sm">
            {data.is_connected ? (
              <>
                <p className="font-semibold text-brand-deep">Terhubung</p>
                <p className="truncate text-ink/55">ID nomor: {data.phone_number_id}</p>
              </>
            ) : (
              <>
                <p className="font-semibold text-ink">Belum terhubung</p>
                <p className="text-ink/55">Nomor bisnis belum bisa membalas pelanggan.</p>
              </>
            )}
          </div>
        </div>
      )}

      {err && <ErrorBox message={err} />}
      {ok && (
        <div className="rounded-2xl bg-brand-tint p-3 text-sm font-medium text-brand-deep ring-1 ring-brand/15">
          WhatsApp berhasil dihubungkan.
        </div>
      )}

      <Card>
        <h2 className="mb-1 font-display text-base font-bold text-ink">Hubungkan via Meta</h2>
        <p className="mb-3 text-sm text-ink/55">Cara cepat — sambungkan nomor WhatsApp bisnismu sekali klik lewat Meta.</p>
        <Button variant="secondary" onClick={launchEmbeddedSignup} disabled={!META_APP_ID || signup.isPending}>
          {signup.isPending ? "..." : "Hubungkan via Meta"}
        </Button>
        {!META_APP_ID && (
          <p className="mt-2 text-xs text-ink/45">Set VITE_META_APP_ID & VITE_META_CONFIG_ID untuk mengaktifkan.</p>
        )}
        {META_APP_ID && !sdkReady && <p className="mt-2 text-xs text-ink/45">Memuat SDK Meta…</p>}
      </Card>

      <Card>
        <h2 className="mb-1 font-display text-base font-bold text-ink">Hubungkan manual</h2>
        <p className="mb-3 text-sm text-ink/55">Alternatif untuk testing — masukkan kredensial Cloud API.</p>
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
          <Button variant="ghost" type="submit" disabled={connect.isPending}>
            {connect.isPending ? "..." : "Hubungkan manual"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
