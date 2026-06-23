import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";
import { toast } from "./lib/toast";

export const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onError: (err) => toast.error((err as Error)?.message || "Terjadi kesalahan, coba lagi."),
    onSuccess: (data, _vars, _ctx, mutation) => {
      const m = (mutation.meta as Record<string, unknown> | undefined)?.successMessage;
      if (typeof m === "string" && m) toast.success(m);
    },
  }),
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
