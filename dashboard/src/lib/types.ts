export interface TokenResponse {
  access_token: string;
  token_type: string;
  business_id: number | null;
  business_name: string | null;
}

export interface OTPRequestResponse {
  code: string;
  expires_at: string;
  instructions: string;
  platform_number: string | null;
}

export interface TopProduct {
  name: string;
  count: number;
}

export interface DashboardSummary {
  orders_today: number;
  revenue_today: number;
  messages_handled: number;
  pending_orders: number;
  top_products: TopProduct[];
}

export type OrderStatus = "baru" | "diproses" | "selesai" | "dibatalkan";

export interface OrderItem {
  name?: string;
  quantity?: number;
  qty?: number;
  price?: number;
}

export interface Order {
  id: number;
  customer_name: string;
  status: OrderStatus;
  total: number;
  items: OrderItem[];
  created_at: string;
}

export interface Product {
  id: number;
  business_id: number;
  name: string;
  price: number;
  description: string | null;
  image_url: string | null;
  created_at: string;
}

export interface FAQItem {
  question: string;
  answer: string;
}

export interface BusinessHours {
  open: string;
  close: string;
}

export interface Settings {
  auto_reply_enabled: boolean;
  greeting_message: string;
  after_hours_message: string;
  business_hours: BusinessHours;
  faq: FAQItem[];
}

export interface WhatsAppConnection {
  is_connected: boolean;
  phone_number_id: string | null;
  waba_id: string | null;
}
