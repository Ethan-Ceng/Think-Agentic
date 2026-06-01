FROM python:3.11-slim AS production

COPY --from=ghcr.io/astral-sh/uv:0.9.22 /uv /uvx /bin/

WORKDIR /app/api

ENV APP_ENV=production
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/api/.venv/bin:$PATH"
ENV TZ=Asia/Shanghai

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . /app/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 5001

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
