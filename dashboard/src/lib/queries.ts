import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { BusinessType, OrderStatus, PaymentMethod, Settings } from "./types";
import { toast } from "./toast";

export const keys = {
  summary: ["summary"] as const,
  orders: (status?: string) => ["orders", status ?? "all"] as const,
  products: ["products"] as const,
  settings: ["settings"] as const,
  business: ["business"] as const,
  whatsapp: ["whatsapp"] as const,
  customers: ["customers"] as const,
  customer: (id: number) => ["customer", id] as const,
  staff: ["staff"] as const,
  bookings: ["bookings"] as const,
};

export const useSummary = () => useQuery({ queryKey: keys.summary, queryFn: api.summary });
export const useOrders = (status?: string) =>
  useQuery({ queryKey: keys.orders(status), queryFn: () => api.orders(status) });
export const useProducts = () => useQuery({ queryKey: keys.products, queryFn: api.products });
export const useSettings = () => useQuery({ queryKey: keys.settings, queryFn: api.settings });
export const useBusiness = () => useQuery({ queryKey: keys.business, queryFn: api.getBusiness });
export const useWhatsapp = () => useQuery({ queryKey: keys.whatsapp, queryFn: api.whatsappStatus });

export function useUpdateOrderStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: OrderStatus }) => api.updateOrderStatus(id, status),
    meta: { successMessage: "Status pesanan diperbarui" },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: keys.summary });
    },
  });
}

type ProductInput = { name: string; price: number; description?: string; image_url?: string; duration_minutes?: number | null };

export function useProductMutations() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: keys.products });
  return {
    create: useMutation({ mutationFn: (d: ProductInput) => api.createProduct(d), meta: { successMessage: "Produk ditambahkan" }, onSuccess: inv }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: number; data: Partial<ProductInput> }) => api.updateProduct(id, data),
      meta: { successMessage: "Produk diperbarui" },
      onSuccess: inv,
    }),
    remove: useMutation({ mutationFn: (id: number) => api.deleteProduct(id), meta: { successMessage: "Produk dihapus" }, onSuccess: inv }),
  };
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: Partial<Settings>) => api.updateSettings(d),
    meta: { successMessage: "Pengaturan disimpan" },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.settings }),
  });
}

export const useCustomers = () => useQuery({ queryKey: keys.customers, queryFn: api.customers });
export const useCustomer = (id: number) =>
  useQuery({ queryKey: keys.customer(id), queryFn: () => api.customer(id) });

export function useUpdateCustomer(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: { notes?: string; tags?: string[]; is_regular_override?: boolean }) => api.updateCustomer(id, d),
    meta: { successMessage: "Catatan pelanggan disimpan" },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.customer(id) });
      qc.invalidateQueries({ queryKey: keys.customers });
    },
  });
}

export function useConnectWhatsapp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: { phone_number_id: string; access_token: string; waba_id?: string }) => api.connectWhatsapp(d),
    meta: { successMessage: "WhatsApp terhubung" },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.whatsapp }),
  });
}

export function useEmbeddedSignup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: { code: string; phone_number_id: string; waba_id: string }) => api.embeddedSignup(d),
    meta: { successMessage: "WhatsApp terhubung" },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.whatsapp }),
  });
}

export function useUpdateBusiness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: { business_name: string; business_type?: BusinessType; payment_methods?: PaymentMethod[]; qris_image_url?: string | null }) =>
      api.updateBusiness(d),
    meta: { successMessage: "Profil bisnis disimpan" },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.business }),
  });
}

export const useStaff = () => useQuery({ queryKey: keys.staff, queryFn: api.listStaff });

export function useCreateStaff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.createStaff(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.staff }),
  });
}

export function useDeleteStaff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteStaff(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.staff }),
  });
}

export function useSendOrderPayment() {
  return useMutation({
    mutationFn: (id: string) => api.sendOrderPayment(id),
    onSuccess: (res) =>
      res.sent
        ? toast.success("Info pembayaran terkirim ✅")
        : toast.error("Gagal kirim. Pastikan metode pembayaran sudah diisi di Pengaturan & pelanggan aktif dalam 24 jam."),
  });
}

export const useBookings = (q?: { status?: string; date?: string }) =>
  useQuery({ queryKey: keys.bookings, queryFn: () => api.listBookings(q) });

export function useUpdateBooking() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, d }: { id: number; d: { status?: string; scheduled_at?: string; staff_id?: number } }) =>
      api.updateBooking(id, d),
    meta: { successMessage: "Booking diperbarui" },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.bookings }),
  });
}

export function useRemindBooking() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.remindBooking(id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: keys.bookings });
      res.sent
        ? toast.success("Pengingat terkirim ✅")
        : toast.error("Pengingat gagal. Pelanggan harus aktif chat dalam 24 jam terakhir.");
    },
  });
}

export function useSendBookingPayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.sendBookingPayment(id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: keys.bookings });
      res.sent
        ? toast.success("Info pembayaran terkirim ✅")
        : toast.error("Gagal kirim. Pastikan metode pembayaran sudah diisi di Pengaturan & pelanggan aktif dalam 24 jam.");
    },
  });
}
