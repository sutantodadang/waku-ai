import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// ponytail: dev runs plain http — manual WhatsApp connect works over http. Meta
// Embedded Signup (FB.login) needs https + a public domain, so it's a
// production-only path; enable basic-ssl + a proxy there, not on localhost.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 3000, host: true },
  // preview serves the built SPA in the container. host:true binds 0.0.0.0;
  // allowedHosts:true lets it answer behind a deploy proxy/custom domain.
  preview: { port: 3000, host: true, allowedHosts: true },
});
