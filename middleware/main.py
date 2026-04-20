"""
Middleware сервис — принимает вебхуки от AlertManager,
фильтрует через filter_rules и отправляет в Gotify.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from filter_rules import AlertContext, evaluate_alert, state_store

# ─── Настройка ────────────────────────────────────────────────────────────────

GOTIFY_URL = os.getenv("GOTIFY_URL", "http://gotify:80")
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("middleware")

app = FastAPI(
    title="Bank Alert Middleware",
    description="Интеллектуальный фильтр алертов для банковской инфраструктуры",
    version="1.0.0",
)

# История обработанных алертов (для UI)
processed_alerts: list[dict] = []

# ─── Модели ───────────────────────────────────────────────────────────────────

class GotifyMessage(BaseModel):
    title: str
    message: str
    priority: int = 5


# ─── Готовый клиент Gotify ────────────────────────────────────────────────────

async def send_to_gotify(title: str, message: str, priority: int = 5) -> bool:
    """Отправляет сообщение в Gotify."""
    token = GOTIFY_TOKEN or os.getenv("GOTIFY_TOKEN", "")
    if not token:
        log.warning("GOTIFY_TOKEN не установлен — пропускаем отправку")
        return False

    url = f"{GOTIFY_URL}/message"
    payload = {"title": title, "message": message, "priority": priority}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"X-Gotify-Key": token},
            )
            resp.raise_for_status()
            log.info(f"Gotify: сообщение доставлено — '{title}'")
            return True
    except httpx.HTTPStatusError as e:
        log.error(f"Gotify HTTP ошибка {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        log.error(f"Gotify недоступен: {e}")
        return False


# ─── Эндпоинты ───────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Принимает вебхук от AlertManager.
    Каждый алерт проходит через фильтр и при необходимости отправляется в Gotify.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Невалидный JSON")

    log.info(f"Получен вебхук: status={body.get('status')}, "
             f"alerts={len(body.get('alerts', []))}")

    results = []

    for raw_alert in body.get("alerts", []):
        labels = raw_alert.get("labels", {})
        annotations = raw_alert.get("annotations", {})
        status = raw_alert.get("status", "firing")
        is_resolved = status == "resolved"

        # Извлекаем числовое значение из описания (если есть)
        value = _extract_value(annotations.get("description", ""))

        ctx = AlertContext(
            alertname=labels.get("alertname", "Unknown"),
            instance=labels.get("instance", "unknown"),
            severity=labels.get("severity", "info"),
            category=labels.get("category", "general"),
            value=value,
            fired_at=_parse_time(raw_alert.get("startsAt")),
            labels=labels,
            annotations=annotations,
        )

        # ── Фильтрация ──────────────────────────────────────────────
        result = evaluate_alert(ctx, is_resolved=is_resolved)

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alertname": ctx.alertname,
            "instance": ctx.instance,
            "severity": ctx.severity,
            "status": status,
            "delivered": result.should_deliver,
            "reason": result.reason,
        }

        if result.should_deliver:
            title = result.modified_title or ctx.annotations.get("summary", ctx.alertname)
            message = result.modified_message or annotations.get("description", "")
            priority = result.priority

            delivered = await send_to_gotify(title, message, priority)
            log_entry["gotify_delivered"] = delivered

            log.info(
                f"[ДОСТАВЛЕНО] {ctx.alertname} @ {ctx.instance} "
                f"(severity={ctx.severity}, priority={priority})"
            )
        else:
            log_entry["gotify_delivered"] = False
            log.info(
                f"[ОТФИЛЬТРОВАНО] {ctx.alertname} @ {ctx.instance} "
                f"— {result.reason}"
            )

        processed_alerts.append(log_entry)
        # Ограничиваем историю
        if len(processed_alerts) > 500:
            processed_alerts.pop(0)

        results.append(log_entry)

    return JSONResponse(content={"processed": len(results), "results": results})


@app.post("/send")
async def manual_send(msg: GotifyMessage):
    """Ручная отправка уведомления в Gotify (для тестирования)."""
    ok = await send_to_gotify(msg.title, msg.message, msg.priority)
    if ok:
        return {"status": "delivered"}
    raise HTTPException(status_code=502, detail="Не удалось доставить в Gotify")


@app.get("/history")
async def get_history(limit: int = 50):
    """История обработанных алертов."""
    return {
        "total": len(processed_alerts),
        "alerts": processed_alerts[-limit:][::-1],
    }


@app.get("/stats")
async def get_stats():
    """Статистика фильтрации."""
    total = len(processed_alerts)
    delivered = sum(1 for a in processed_alerts if a.get("delivered"))
    filtered = total - delivered

    by_severity: dict[str, int] = {}
    by_instance: dict[str, int] = {}

    for a in processed_alerts:
        sev = a.get("severity", "unknown")
        inst = a.get("instance", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_instance[inst] = by_instance.get(inst, 0) + 1

    return {
        "total_processed": total,
        "delivered": delivered,
        "filtered_out": filtered,
        "delivery_rate": f"{(delivered / total * 100):.1f}%" if total > 0 else "0%",
        "by_severity": by_severity,
        "by_instance": by_instance,
    }


@app.get("/health")
async def health():
    """Проверка состояния middleware."""
    gotify_ok = await _check_gotify()
    return {
        "status": "ok",
        "gotify_reachable": gotify_ok,
        "gotify_token_set": bool(GOTIFY_TOKEN),
        "processed_total": len(processed_alerts),
    }


@app.get("/")
async def root():
    return {
        "service": "Bank Alert Middleware",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "POST /webhook — приём алертов от AlertManager",
            "send": "POST /send — ручная отправка в Gotify",
            "history": "GET /history — история алертов",
            "stats": "GET /stats — статистика фильтрации",
            "health": "GET /health — состояние сервиса",
            "docs": "GET /docs — Swagger UI",
        },
    }


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _parse_time(ts: Optional[str]) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        from dateutil import parser as dtparser
        return dtparser.parse(ts)
    except Exception:
        return datetime.now(timezone.utc)


def _extract_value(description: str) -> Optional[float]:
    """Пытается извлечь числовое значение из описания алерта."""
    import re
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", description)
    if matches:
        try:
            return float(matches[0])
        except ValueError:
            pass
    return None


async def _check_gotify() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{GOTIFY_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False