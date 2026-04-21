from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import requests
import os
import time
from datetime import datetime

app = FastAPI(title="Bank Smart Alert Middleware")

GOTIFY_URL = "http://gotify:8080/message"
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN")

# Внутренняя память Middleware (хранится в оперативной памяти контейнера)
alert_history = {}

class AlertData(BaseModel):
    status: str
    labels: dict
    annotations: dict

def is_business_hours() -> bool:
    """Проверяет, находится ли сейчас время в 'рабочие часы' (9:00 - 18:00 по будням)"""
    now = datetime.now()
    # 0 - Понедельник, 6 - Воскресенье
    if now.weekday() >= 5: 
        return False
    if 9 <= now.hour < 18: 
        return True
    return False

def check_flapping(alert_name: str, current_status: str) -> dict:
    """
    ФИШКА 1: Защита от флаппинга (дребезга).
    Если алерт меняет статус (firing/resolved) более 2 раз за 3 минуты - это флаппинг.
    """
    current_time = time.time()
    FLAP_WINDOW = 180 # 3 минуты
    FLAP_THRESHOLD = 2 # кол-во переключений
    
    if alert_name not in alert_history:
        alert_history[alert_name] = {"states": [current_status], "last_time": current_time, "is_flapping": False}
        return {"is_flapping": False, "just_started": False}

    history = alert_history[alert_name]
    
    # Очищаем старую историю (выход за окно в 3 минуты)
    history["states"] = [s for s in history["states"] if (current_time - history["last_time"]) < FLAP_WINDOW]
    
    # Добавляем текущий статус
    history["states"].append(current_status)
    history["last_time"] = current_time

    # Считаем количество смен статуса (если текущий не равен предыдущему)
    state_changes = 0
    for i in range(1, len(history["states"])):
        if history["states"][i] != history["states"][i-1]:
            state_changes += 1

    just_started_flapping = False
    
    if state_changes >= FLAP_THRESHOLD:
        if not history["is_flapping"]:
            just_started_flapping = True # Только что вошел в состояние флаппинга
        history["is_flapping"] = True
    else:
        # Если алерт стабилизировался (например, нагрузка упала вообще)
        if history["is_flapping"] and current_status == "resolved":
            history["is_flapping"] = False
            history["states"] = [] # Сбрасываем историю

    return {"is_flapping": history["is_flapping"], "just_started": just_started_flapping}

def send_to_gotify(title: str, message: str, priority: int):
    """Вспомогательная функция отправки в Gotify"""
    try:
        requests.post(
            f"{GOTIFY_URL}?token={GOTIFY_TOKEN}",
            json={"title": title, "message": message, "priority": priority}
        )
    except Exception as e:
        print(f"[MIDDLEWARE] Ошибка отправки в Gotify: {e}")

@app.post("/alert")
async def handle_alert(request: Request):
    if not GOTIFY_TOKEN or GOTIFY_TOKEN == "YOUR_TOKEN_HERE":
        raise HTTPException(status_code=500, detail="Gotify token is not configured")

    body = await request.json()
    alerts = body.get("alerts", [])
    
    delivered = 0
    filtered = 0

    for alert_data in alerts:
        alert = AlertData(
            status=alert_data.get("status"),
            labels=alert_data.get("labels", {}),
            annotations=alert_data.get("annotations", {})
        )

        alert_name = alert.labels.get("alertname", "Unknown")
        severity = alert.labels.get("severity", "info")
        summary = alert.annotations.get("summary", alert_name)

        # ==========================================
        # ФИШКА 2: Ночной режим (Тихие часы)
        # ==========================================
        if not is_business_hours() and severity == "warning":
            print(f"[MIDDLEWARE] 🌙 НОЧНОЙ РЕЖИМ: Warning алерт '{alert_name}' проигнорирован до утра.")
            filtered += 1
            continue

        # ==========================================
        # ФИШКА 1: Проверка на Флаппинг
        # ==========================================
        flap_info = check_flapping(alert_name, alert.status)
        
        if flap_info["is_flapping"]:
            if flap_info["just_started"]:
                # Алерт начал дребезжать только что. Шлем ОДНО уведомление об этом и замолкаем
                send_to_gotify(
                    title=f"⚠️ FLAPPING: {summary}",
                    message="Алерт хаотично меняет статус. Система перешла в режим подавления шума. Вы будете уведомлены при стабилизации.",
                    priority=6
                )
                delivered += 1
            else:
                # Продолжает дребезжать - просто молчим, не спамим Gotify
                print(f"[MIDDLEWARE] 🔇 ПОДАВЛЕНО (FLAPPING): {alert_name}")
                filtered += 1
            continue

        # Если мы здесь, значит алерт нормальный (не флаппинг и не отфильтрован ночью)
        
        if alert.status == "resolved":
            send_to_gotify(
                title=f"🟢 РЕШЕНО: {summary}",
                message="Метрики вернулись в норму. Нагрузка снизилась ниже допустимого порога.",
                priority=2
            )
            delivered += 1
        else:
            # Формируем обычный алерт
            priority = 8 if severity == "critical" else 5
            emoji = "🔴" if severity == "critical" else "🟡"
            send_to_gotify(
                title=f"{emoji} Банк: {summary}",
                message=alert.annotations.get('description', 'Нет описания'),
                priority=priority
            )
            delivered += 1

    return {"status": "ok", "delivered": delivered, "filtered_as_noise": filtered}