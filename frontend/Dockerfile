FROM node:22-alpine AS builder
WORKDIR /app

ARG VITE_API_BASE_URL=/api
ARG VITE_WS_BASE_URL=/ws
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_BASE_URL=${VITE_WS_BASE_URL}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD \
    wget -qO- http://127.0.0.1/ >/dev/null || exit 1
