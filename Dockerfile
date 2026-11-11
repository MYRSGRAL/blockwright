FROM python:3.12-slim-bookworm AS python-build
WORKDIR /src
RUN python -m venv /opt/venv
COPY pyproject.toml README.md LICENSE ./
COPY blockwright/ ./blockwright/
RUN /opt/venv/bin/pip install --no-cache-dir --no-compile . \
    && find /opt/venv -type f -name '*.pyc' -delete \
    && find /opt/venv -type d -name __pycache__ -empty -delete

FROM python:3.12-slim-bookworm AS runtime-base
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates librsvg2-bin fonts-liberation2 \
    && find /var/lib/apt/lists -mindepth 1 -delete \
    && groupadd --gid 10001 bot \
    && useradd --uid 10001 --gid bot --no-create-home --home-dir /tmp bot

FROM golang:1.25.12 AS bot-build
WORKDIR /src
COPY telegram-bot/go.mod ./
COPY telegram-bot/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/telegram-bot .

FROM runtime-base AS runtime
COPY --from=python-build /opt/venv /opt/venv
COPY --from=bot-build /out/telegram-bot /usr/local/bin/telegram-bot
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp
WORKDIR /tmp
USER 10001:10001
STOPSIGNAL SIGTERM
ENTRYPOINT ["telegram-bot"]
