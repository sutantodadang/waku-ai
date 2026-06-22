import { authStore } from "./auth";
import type {
  DashboardSummary,
  OTPRequestResponse,
  Order,
  OrderStatus,
  Product,
  Settings,
  TokenResponse,
  WhatsAppConnection,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((opts.headers as Record<string, string>) ?? {}),
  };
  const t = authStore.getToken();
  if (t) headers["Authorization"] = `Bearer ${t}`;

  let res: Response;
  try {
    res = await fetch(BASE + path, { ...opts, headers });
  } catch {
    throw new ApiError(0, "Tidak bisa terhubung ke server Waku.");
  }

  if (res.status === 401) {
    authStore.clear();
    throw new ApiError(401, "Sesi berakhir. Silakan login lagi.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null as T;
  return (await res.json()) as T;
}

const body = (data: unknown): RequestInit => ({ body: JSON.stringify(data) });

export const api = {
  // ── Auth ──
  register: (d: { email: string; password: string; business_name: string; phone_number: string }) =>
    req<TokenResponse>("/api/auth/register", { method: "POST", ...body(d) }),
  login: (d: { email: string; password: string }) =>
    req<TokenResponse>("/api/auth/login", { method: "POST", ...body(d) }),
  otpRequest: (d: { phone_number: string; purpose?: string }) =>
    req<OTPRequestResponse>("/api/auth/otp/request", { method: "POST", ...body(d) }),
  otpVerify: (d: { phone_number: string; code: string }) =>
    req<TokenResponse>("/api/auth/otp/verify", { method: "POST", ...body(d) }),

  // ── Dashboard ──
  summary: () => req<DashboardSummary>("/api/dashboard/summary"),
  orders: (status?: string) => req<Order[]>(`/api/orders${status ? `?status=${status}` : ""}`),
  updateOrderStatus: (id: number, status: OrderStatus) =>
    req<Order>(`/api/orders/${id}`, { method: "PATCH", ...body({ status }) }),

  // ── Catalog ──
  products: () => req<Product[]>("/api/products"),
  createProduct: (d: { name: string; price: number; description?: string; image_url?: string }) =>
    req<Product>("/api/products", { method: "POST", ...body(d) }),
  updateProduct: (id: number, d: Partial<{ name: string; price: number; description: string; image_url: string }>) =>
    req<Product>(`/api/products/${id}`, { method: "PUT", ...body(d) }),
  deleteProduct: (id: number) => req<unknown>(`/api/products/${id}`, { method: "DELETE" }),

  // ── Settings + business ──
  settings: () => req<Settings>("/api/settings"),
  updateSettings: (d: Partial<Settings>) => req<Settings>("/api/settings", { method: "PUT", ...body(d) }),
  renameBusiness: (business_name: string) =>
    req<{ business_name: string }>("/api/business", { method: "PATCH", ...body({ business_name }) }),

  // ── WhatsApp ──
  whatsappStatus: () => req<WhatsAppConnection>("/api/whatsapp/status"),
  connectWhatsapp: (d: { phone_number_id: string; access_token: string; waba_id?: string }) =>
    req<WhatsAppConnection>("/api/whatsapp/connect", { method: "PUT", ...body(d) }),
  embeddedSignup: (d: { code: string; phone_number_id: string; waba_id: string }) =>
    req<WhatsAppConnection>("/api/whatsapp/embedded-signup", { method: "POST", ...body(d) }),

  // ── Upload (multipart) ──
  async upload(file: File): Promise<string> {
    const fd = new FormData();
    fd.append("file", file);
    const t = authStore.getToken();
    const res = await fetch(BASE + "/api/upload", {
      method: "POST",
      headers: t ? { Authorization: `Bearer ${t}` } : {},
      body: fd,
    });
    if (!res.ok) throw new ApiError(res.status, "Gagal mengupload gambar.");
    const data = (await res.json()) as { url: string };
    return BASE + data.url;
  },
};
