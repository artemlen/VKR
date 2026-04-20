"""
Модуль правил фильтрации алертов.
Здесь описана логика middleware — "умного" фильтра уведомлений.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AlertContext:
    """Контекст одного алерта для принятия решения о доставке."""
    alertname: str
    instance: str
    severity: str
    category: str
    value: Optional[float]
    fired_at: datetime
    labels: dict
    annotations: dict


@dataclass
class FilterResult:
    """Результат фильтрации."""
    should_deliver: bool
    reason: str
    priority: int = 5          # 1 (высший) … 10 (низший)
    modified_title: Optional[str] = None
    modified_message: Optional[str] = None


# ─── Хранилище состояния (in-memory) ─────────────────────────────────────────

class AlertStateStore:
    """
    Хранит историю алертов для дедупликации и подавления шума.
    В продакшне стоит заменить на Redis.
    """

    def __init__(self):
        # instance -> alertname -> timestamp последней доставки
        self._last_delivered: dict[str, dict[str, float]] = {}
        # instance -> alertname -> количество повторений
        self._repeat_count: dict[str, dict[str, int]] = {}
        # Отслеживание статуса resolved
        self._resolved_sent: dict[str, dict[str, bool]] = {}

    def get_last_delivered(self, instance: str, alertname: str) -> Optional[float]:
        return self._last_delivered.get(instance, {}).get(alertname)

    def record_delivery(self, instance: str, alertname: str):
        if instance not in self._last_delivered:
            self._last_delivered[instance] = {}
            self._repeat_count[instance] = {}
        self._last_delivered[instance][alertname] = time.time()
        self._repeat_count[instance][alertname] = \
            self._repeat_count[instance].get(alertname, 0) + 1

    def get_repeat_count(self, instance: str, alertname: str) -> int:
        return self._repeat_count.get(instance, {}).get(alertname, 0)

    def mark_resolved(self, instance: str, alertname: str):
        if instance not in self._resolved_sent:
            self._resolved_sent[instance] = {}
        self._resolved_sent[instance][alertname] = True
        # Сбрасываем счётчики
        if instance in self._last_delivered:
            self._last_delivered[instance].pop(alertname, None)
        if instance in self._repeat_count:
            self._repeat_count[instance].pop(alertname, None)


# Singleton
state_store = AlertStateStore()


# ─── Конфигурация порогов ────────────────────────────────────────────────────

# Минимальный интервал повторной отправки (секунды) по severity
REPEAT_INTERVAL = {
    "critical": 120,    # раз в 2 минуты
    "warning": 600,     # раз в 10 минут
    "info": 1800,       # раз в 30 минут
}

# Приоритет gotify по severity
GOTIFY_PRIORITY = {
    "critical": 9,
    "warning": 5,
    "info": 2,
}

# Алерты которые ВСЕГДА доставляются (независимо от дедупликации)
ALWAYS_DELIVER = {"NodeDown", "CriticalCPUUsage", "CriticalMemoryUsage"}

# Алерты которые игнорируются полностью
NEVER_DELIVER = set()  # можно добавить шумные алерты


# ─── Основная логика фильтрации ───────────────────────────────────────────────

def evaluate_alert(ctx: AlertContext, is_resolved: bool = False) -> FilterResult:
    """
    Главная функция фильтрации.
    Возвращает FilterResult с решением о доставке.
    """

    # 1. Resolved-уведомления всегда доставляем (если алерт был отправлен)
    if is_resolved:
        last = state_store.get_last_delivered(ctx.instance, ctx.alertname)
        if last is not None:
            state_store.mark_resolved(ctx.instance, ctx.alertname)
            return FilterResult(
                should_deliver=True,
                reason="resolved — проблема устранена",
                priority=4,
                modified_title=f"✅ УСТРАНЕНО: {ctx.alertname} на {ctx.instance}",
                modified_message=_build_resolved_message(ctx),
            )
        else:
            return FilterResult(
                should_deliver=False,
                reason="resolved для алерта который не был доставлен — пропускаем",
            )

    # 2. Никогда не доставляем заблокированные алерты
    if ctx.alertname in NEVER_DELIVER:
        return FilterResult(
            should_deliver=False,
            reason=f"алерт {ctx.alertname} в списке игнорирования",
        )

    # 3. Критические алерты — всегда доставляем немедленно
    if ctx.alertname in ALWAYS_DELIVER:
        state_store.record_delivery(ctx.instance, ctx.alertname)
        return FilterResult(
            should_deliver=True,
            reason="критический алерт — доставка обязательна",
            priority=GOTIFY_PRIORITY.get(ctx.severity, 5),
            modified_title=_build_title(ctx),
            modified_message=_build_message(ctx),
        )

    # 4. Дедупликация: проверяем интервал повторной отправки
    last_delivered = state_store.get_last_delivered(ctx.instance, ctx.alertname)
    if last_delivered is not None:
        min_interval = REPEAT_INTERVAL.get(ctx.severity, 300)
        elapsed = time.time() - last_delivered
        if elapsed < min_interval:
            return FilterResult(
                should_deliver=False,
                reason=(
                    f"дедупликация: алерт уже был отправлен "
                    f"{int(elapsed)}с назад, минимальный интервал {min_interval}с"
                ),
            )

    # 5. Первая отправка или интервал истёк
    repeat_count = state_store.get_repeat_count(ctx.instance, ctx.alertname)
    state_store.record_delivery(ctx.instance, ctx.alertname)

    return FilterResult(
        should_deliver=True,
        reason=f"новый алерт (повторений: {repeat_count})",
        priority=GOTIFY_PRIORITY.get(ctx.severity, 5),
        modified_title=_build_title(ctx, repeat_count),
        modified_message=_build_message(ctx, repeat_count),
    )


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _severity_emoji(severity: str) -> str:
    return {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")


def _build_title(ctx: AlertContext, repeat_count: int = 0) -> str:
    emoji = _severity_emoji(ctx.severity)
    repeat_str = f" (повтор #{repeat_count + 1})" if repeat_count > 0 else ""
    return f"{emoji} {ctx.annotations.get('summary', ctx.alertname)}{repeat_str}"


def _build_message(ctx: AlertContext, repeat_count: int = 0) -> str:
    description = ctx.annotations.get("description", "Нет описания")
    runbook = ctx.annotations.get("runbook", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"**Сервер:** {ctx.instance}",
        f"**Серьёзность:** {ctx.severity.upper()}",
        f"**Категория:** {ctx.category}",
        f"**Время:** {ts}",
        "",
        f"{description}",
    ]
    if runbook:
        lines.append(f"\n**Документация:** {runbook}")
    if repeat_count > 0:
        lines.append(f"\n⚠️ Проблема не устранена. Это уведомление #{repeat_count + 1}.")
    return "\n".join(lines)


def _build_resolved_message(ctx: AlertContext) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        f"**Сервер:** {ctx.instance}\n"
        f"**Алерт:** {ctx.alertname}\n"
        f"**Время устранения:** {ts}\n\n"
        f"Проблема на сервере **{ctx.instance}** устранена. "
        f"Все параметры вернулись в норму."
    )