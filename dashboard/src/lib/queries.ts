import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { OrderStatus, Settings } from "./types";

export const keys = {
  summary: ["summary"] as const,
  orders: (status?: string) => ["orders", status ?? "all"] as const,
  products: ["products"] as const,
  settings: ["settings"] as const,
  whatsapp: ["whatsapp"] as const,
};

export const useSummary = () => useQuery({ queryKey: keys.summary, queryFn: api.summary });
export const useOrders = (status?: string) =>
  useQuery({ queryKey: keys.orders(status), queryFn: () => api.orders(status) });
export const useProducts = () => useQuery({ queryKey: keys.products, queryFn: api.products });
export const useSettings = () => useQuery({ queryKey: keys.settings, queryFn: api.settings });
export const useWhatsapp = () => useQuery({ queryKey: keys.whatsapp, queryFn: api.whatsappStatus });

export function useUpdateOrderStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: OrderStatus }) => api.updateOrderStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: keys.summary });
    },
  });
}

type ProductInput = { name: string; price: number; description?: string; image_url?: string };

export function useProductMutations() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: keys.products });
  return {
    create: useMutation({ mutationFn: (d: ProductInput) => api.createProduct(d), onSuccess: inv }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: number; data: Partial<ProductInput> }) => api.updateProduct(id, data),
      onSuccess: inv,
    }),
    remove: useMutation({ mutationFn: (id: number) => api.deleteProduct(id), onSuccess: inv }),
  };
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: Partial<Settings>) => api.updateSettings(d),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.settings }),
  });
}

export function useConnectWhatsapp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: { phone_number_id: string; access_token: string; waba_id?: string }) => api.connectWhatsapp(d),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.whatsapp }),
  });
}
