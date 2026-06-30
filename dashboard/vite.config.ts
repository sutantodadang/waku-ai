import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// ponytail: dev runs plain http — manual WhatsApp connect works over http. Meta
// Embedded Signup (FB.login) needs https + a public domain, so it's a
// production-only path; enable basic-ssl + a proxy there, not on localhost.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 3000, host: true },
  // preview serves the built SPA in the container. host:true binds 0.0.0.0.
  // Lock Host validation in prod via DASHBOARD_ALLOWED_HOSTS (comma-separated,
  // e.g. "dashboard.example.com"); falls back to permissive only when unset.
  preview: {
    port: 3000,
    host: true,
    allowedHosts: process.env.DASHBOARD_ALLOWED_HOSTS?.split(",") ?? true,
  },
});
