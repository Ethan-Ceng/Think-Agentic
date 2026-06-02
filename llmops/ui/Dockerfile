FROM node:20 AS builder

WORKDIR /app/web

COPY package.json pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate && pnpm install --frozen-lockfile

COPY . .

ENV VITE_API_PREFIX=/api
RUN pnpm build

FROM nginx:alpine AS production

COPY --from=builder /app/web/dist /usr/share/nginx/html
COPY --from=builder /app/web/docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf

RUN find /usr/share/nginx/html -type d -exec chmod 755 {} \;
RUN find /usr/share/nginx/html -type f -exec chmod 644 {} \;

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
