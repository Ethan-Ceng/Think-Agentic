# MoocManus Web

Vue 3 + TypeScript + Vite implementation of the MoocManus frontend.

## Scripts

```sh
pnpm install
pnpm dev
pnpm build
pnpm preview
```

Set `VITE_API_BASE_URL` to override the backend API address. It defaults to `http://localhost:8000/api`.

## Container

```sh
docker build --build-arg VITE_API_BASE_URL=/api -t mooc-manus-web .
docker run --rm -p 8080:80 mooc-manus-web
```

The container serves the Vite build with nginx and exposes `/healthz` for health checks.
