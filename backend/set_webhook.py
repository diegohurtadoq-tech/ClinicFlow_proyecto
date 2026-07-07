"""Registra el webhook de Telegram para el despliegue en Vercel."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from urllib.parse import quote


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    base_url = os.getenv("VERCEL_PUBLIC_URL", "").strip()

    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN no configurado")
    if not base_url:
        raise SystemExit("VERCEL_PUBLIC_URL no configurado. Ejemplo: https://clinic-flow-proyecto.vercel.app")

    webhook_url = f"{base_url.rstrip('/')}/api/telegram/webhook"
    url = f"https://api.telegram.org/bot{token}/setWebhook?url={quote(webhook_url, safe='')}"

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"No se pudo contactar a Telegram: {exc}") from exc

    print(payload)
    if payload.get("ok"):
        print(f"Webhook registrado correctamente: {webhook_url}")
    else:
        raise SystemExit(f"No se pudo registrar el webhook: {payload}")


if __name__ == "__main__":
    sys.exit(main())
