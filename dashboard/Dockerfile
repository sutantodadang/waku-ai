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

# Serve the built SPA with nginx (production static server, not vite preview).
FROM nginx:alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
# nginx's entrypoint renders this template, substituting ${PORT} only.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV PORT=3000
EXPOSE 3000
# Default nginx CMD (the base image entrypoint runs envsubst then starts nginx).
