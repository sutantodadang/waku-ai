import { useState, type FormEvent } from "react";
import { api, ApiError } from "../lib/api";
import { authStore } from "../lib/auth";
import { Button, ErrorBox, Field, inputCls } from "../components/ui";
import type { OTPRequestResponse, TokenResponse } from "../lib/types";

type Tab = "login" | "register" | "otp";

export default function AuthPage() {
  const [tab, setTab] = useState<Tab>("login");
  const [err, setErr] = useState("");

  const done = (t: TokenResponse) => {
    setErr("");
    authStore.setSession(t.access_token, t.business_name);
  };
  const fail = (e: unknown) => setErr(e instanceof ApiError ? e.message : "Terjadi kesalahan.");

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-5">
      <div className="mb-6 text-center">
        <div className="text-3xl font-extrabold text-teal-dark">Waku 🤖</div>
        <p className="text-sm text-gray-500">Asisten WhatsApp pintar untuk UMKM</p>
      </div>
      <div className="mb-4 grid grid-cols-3 rounded-full bg-gray-100 p-1 text-sm font-semibold">
        {(["login", "register", "otp"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setErr("");
            }}
            className={`rounded-full py-2 ${tab === t ? "bg-white text-orange shadow" : "text-gray-500"}`}
          >
            {t === "login" ? "Masuk" : t === "register" ? "Daftar" : "OTP WA"}
          </button>
        ))}
      </div>
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      <div className="rounded-2xl bg-white p-5 shadow-sm">
        {tab === "login" && <LoginForm onDone={done} onError={fail} />}
        {tab === "register" && <RegisterForm onDone={done} onError={fail} />}
        {tab === "otp" && <OtpForm onDone={done} onError={fail} />}
      </div>
    </div>
  );
}

type FormProps = { onDone: (t: TokenResponse) => void; onError: (e: unknown) => void };

function LoginForm({ onDone, onError }: FormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      onDone(await api.login({ email, password }));
    } catch (x) {
      onError(x);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <Field label="Email">
        <input className={inputCls} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </Field>
      <Field label="Password">
        <input className={inputCls} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </Field>
      <Button type="submit" disabled={busy}>{busy ? "..." : "Masuk"}</Button>
    </form>
  );
}

function RegisterForm({ onDone, onError }: FormProps) {
  const [businessName, setBusinessName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      onDone(await api.register({ email, password, business_name: businessName, phone_number: phone }));
    } catch (x) {
      onError(x);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <Field label="Nama Bisnis">
        <input className={inputCls} value={businessName} onChange={(e) => setBusinessName(e.target.value)} placeholder="Warung Makmur" required />
      </Field>
      <Field label="Nomor WhatsApp">
        <input className={inputCls} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="081234567890" required />
      </Field>
      <Field label="Email">
        <input className={inputCls} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </Field>
      <Field label="Password (min. 6)">
        <input className={inputCls} type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} required />
      </Field>
      <Button type="submit" disabled={busy}>{busy ? "..." : "Daftar"}</Button>
    </form>
  );
}

function OtpForm({ onDone, onError }: FormProps) {
  const [phone, setPhone] = useState("");
  const [info, setInfo] = useState<OTPRequestResponse | null>(null);
  const [busy, setBusy] = useState(false);
  async function request() {
    setBusy(true);
    try {
      setInfo(await api.otpRequest({ phone_number: phone, purpose: "login" }));
    } catch (x) {
      onError(x);
    } finally {
      setBusy(false);
    }
  }
  async function verify() {
    if (!info) return;
    setBusy(true);
    try {
      onDone(await api.otpVerify({ phone_number: phone, code: info.code }));
    } catch (x) {
      onError(x);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500">
        Login lewat WhatsApp (gratis). Minta kode, kirim dari WA Anda ke nomor Waku, lalu verifikasi.
      </p>
      <Field label="Nomor WhatsApp Anda">
        <input className={inputCls} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="081234567890" />
      </Field>
      {!info && (
        <Button variant="secondary" onClick={request} disabled={busy || !phone}>{busy ? "..." : "1) Minta Kode"}</Button>
      )}
      {info && (
        <>
          <div className="space-y-2 rounded-xl bg-teal-light p-3 text-sm">
            <div className="font-semibold">Kirim kode ini:</div>
            <div className="rounded-lg bg-white px-3 py-2 font-mono text-lg">{info.code}</div>
            <div className="font-semibold">Ke nomor WhatsApp Waku:</div>
            <div className="rounded-lg bg-white px-3 py-2 font-mono">{info.platform_number ?? "(nomor platform belum di-set)"}</div>
            <p className="text-gray-600">{info.instructions}</p>
          </div>
          <Button onClick={verify} disabled={busy}>{busy ? "..." : "2) Saya Sudah Kirim — Verifikasi"}</Button>
        </>
      )}
    </div>
  );
}
