from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import requests
import os

app = FastAPI(title="Bank Smart Alert Middleware")

# Читаем токен из переменных окружения
GOTIFY_URL = "http://gotify:8080/message"
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN")

class AlertData(BaseModel):
    status: str
    labels: dict
    annotations: dict

def is_noise(alert: AlertData) -> bool:
    """
    ТВОЯ ФИШКА ДЛЯ ВКР ЗДЕСЬ.
    Сейчас реализована базовая логика: пропускаем Critical, фильтруем Warning (как шум),
    если они не содержат ключевых слов.
    Ты можешь внедрить сюда ML, тайм-ауты, анализ истории и т.д.
    """
    severity = alert.labels.get("severity", "")
    alert_name = alert.labels.get("alertname", "")
    description = alert.annotations.get("description", "")

    # Пример 1: Фильтруем конкретные алерты, которые мы считаем информационным шумом
    if alert_name == "SomeBoringAlert":
        print(f"[MIDDLEWARE] Отфильтрован шум: {alert_name}")
        return True

    # Пример 2: Пропускаем всё, что критично
    if severity == "critical":
        return False

    # Пример 3: Warning пропускаем только если есть слово RAM (иначе это шум)
    if severity == "warning" and "RAM" in description:
        return False

    # Остальное считаем шумом
    print(f"[MIDDLEWARE] Отфильтрован как шум: {alert_name} (Severity: {severity})")
    return True

@app.post("/alert")
async def handle_alert(request: Request):
    if not GOTIFY_TOKEN or GOTIFY_TOKEN == "YOUR_TOKEN_HERE":
        raise HTTPException(status_code=500, detail="Gotify token is not configured in .env")

    body = await request.json()
    
    # Alertmanager присылает список алертов
    alerts = body.get("alerts", [])
    processed_count = 0
    filtered_count = 0

    for alert_data in alerts:
        alert = AlertData(
            status=alert_data.get("status"),
            labels=alert_data.get("labels", {}),
            annotations=alert_data.get("annotations", {})
        )

        if is_noise(alert):
            filtered_count += 1
            continue

        # Формируем сообщение для Gotify
        if alert.status == "resolved":
            # Если проблема УСТРАНЕНА, меняем текст на логичный
            title = f"🟢 РЕШЕНО: {alert.annotations.get('summary', 'Алерт')}"
            #message = f"Восстановлена нормальная работа. Последнее значение: {alert.annotations.get('description', '')}"
            message = "Метрики вернулись в норму. Нагрузка снизилась ниже допустимого порога."
            priority = 2 # Понижаем приоритет, чтобы не пиликало
        else:
            # Если проблема ЕСТЬ, шлем стандартный текст
            status_emoji = "🔴"
            title = f"{status_emoji} Банк: {alert.annotations.get('summary', 'Алерт')}"
            message = alert.annotations.get('description', 'Нет описания')
            priority = 8 if alert.labels.get("severity") == "critical" else 5

        # Отправляем в Gotify
        try:
            resp = requests.post(
                f"{GOTIFY_URL}?token={GOTIFY_TOKEN}",
                json={
                    "title": title,
                    "message": message,
                    "priority": priority
                }
            )
            if resp.status_code == 200:
                processed_count += 1
                print(f"[MIDDLEWARE] Доставлено: {title}")
            else:
                print(f"[MIDDLEWARE] Ошибка Gotify: {resp.text}")
        except Exception as e:
            print(f"[MIDDLEWARE] Ошибка соединения с Gotify: {e}")

    return {"status": "ok", "delivered": processed_count, "filtered_as_noise": filtered_count}