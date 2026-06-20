# Waku Dashboard — Bun + Vite + React (SPA)
FROM oven/bun:1 AS build
WORKDIR /app
COPY package.json bun.lock* ./
RUN bun install
COPY . .
# Vite inlines env at build time — set the public backend URL here.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN bun run build

FROM oven/bun:1-slim AS runtime
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json /app/vite.config.ts ./
EXPOSE 8501
# vite preview serves dist/ with SPA fallback (client-side routing).
CMD ["bun", "run", "preview"]
