from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import requests
import os
import time
from datetime import datetime

app = FastAPI(title="Bank Smart Alert Middleware")

GOTIFY_URL = "http://gotify:8080/message"
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN")

# Внутренняя память Middleware
alert_history = {}
maintenance_mode = False
deduplication_enabled = True # <--- НОВОЕ: Флаг дедупликации

# Настройки дедупликации
DEDUP_INTERVAL = 300 # 5 минут

class AlertData(BaseModel):
    status: str
    labels: dict
    annotations: dict

# ==========================================
# API для управления Middleware
# ==========================================
@app.post("/api/maintenance/on")
async def enable_maintenance():
    global maintenance_mode
    maintenance_mode = True
    return {"status": "ok", "message": "Режим обслуживания ВКЛЮЧЕН."}

@app.post("/api/maintenance/off")
async def disable_maintenance():
    global maintenance_mode
    maintenance_mode = False
    return {"status": "ok", "message": "Режим обслуживания ВЫКЛЮЧЕН."}

# НОВЫЕ API ЭНДПОИНТЫ
@app.post("/api/dedup/off")
async def disable_dedup():
    global deduplication_enabled
    deduplication_enabled = False
    return {"status": "ok", "message": "Дедупликация ВЫКЛЮЧЕНА. Повторные алерты будут приходить каждую минуту."}

@app.post("/api/dedup/on")
async def enable_dedup():
    global deduplication_enabled
    deduplication_enabled = True
    return {"status": "ok", "message": "Дедупликация ВКЛЮЧЕНА (интервал 5 мин)."}

@app.get("/api/status")
async def get_status():
    return {
        "maintenance_mode": maintenance_mode,
        "deduplication_enabled": deduplication_enabled
    }

def is_business_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5: return False
    if 9 <= now.hour < 18: return True
    return False

def check_flapping(alert_name: str, current_status: str) -> dict:
    current_time = time.time()
    FLAP_WINDOW = 180
    FLAP_THRESHOLD = 2
    
    if alert_name not in alert_history:
        alert_history[alert_name] = {"states": [current_status], "last_time": current_time, "is_flapping": False}
        return {"is_flapping": False, "just_started": False}

    history = alert_history[alert_name]
    history["states"] = [s for s in history["states"] if (current_time - history["last_time"]) < FLAP_WINDOW]
    history["states"].append(current_status)
    history["last_time"] = current_time

    state_changes = sum(1 for i in range(1, len(history["states"])) if history["states"][i] != history["states"][i-1])
    just_started_flapping = False
    
    if state_changes >= FLAP_THRESHOLD:
        if not history["is_flapping"]: just_started_flapping = True
        history["is_flapping"] = True
    else:
        if history["is_flapping"] and current_status == "resolved":
            history["is_flapping"] = False
            history["states"] = []

    return {"is_flapping": history["is_flapping"], "just_started": just_started_flapping}

def send_to_gotify(title: str, message: str, priority: int):
    try:
        requests.post(f"{GOTIFY_URL}?token={GOTIFY_TOKEN}", json={"title": title, "message": message, "priority": priority})
    except Exception as e:
        print(f"[MIDDLEWARE] Ошибка Gotify: {e}")

@app.post("/alert")
async def handle_alert(request: Request):
    if not GOTIFY_TOKEN or GOTIFY_TOKEN == "YOUR_TOKEN_HERE":
        raise HTTPException(status_code=500, detail="Gotify token error")

    body = await request.json()
    alerts = body.get("alerts", [])
    
    delivered = 0
    filtered = 0
    repeats_suppressed = 0

    for alert_data in alerts:
        alert = AlertData(
            status=alert_data.get("status"),
            labels=alert_data.get("labels", {}),
            annotations=alert_data.get("annotations", {})
        )

        alert_name = alert.labels.get("alertname", "Unknown")
        severity = alert.labels.get("severity", "info")
        summary = alert.annotations.get("summary", alert_name)

        if maintenance_mode and severity != "critical":
            print(f"[MIDDLEWARE] 🔧 ОБСЛУЖИВАНИЕ: '{alert_name}' проигнорирован.")
            filtered += 1
            continue

        if not is_business_hours() and severity == "warning":
            print(f"[MIDDLEWARE] 🌙 НОЧНОЙ РЕЖИМ: '{alert_name}' отложен.")
            filtered += 1
            continue

        flap_info = check_flapping(alert_name, alert.status)
        if flap_info["is_flapping"]:
            if flap_info["just_started"]:
                send_to_gotify(title=f"⚠️ FLAPPING: {summary}", message="Обнаружен хаотичный сдвиг статуса. Шум подавлен.", priority=6)
                delivered += 1
            else:
                filtered += 1
            continue

        # Дедупликация (теперь с проверкой флага!)
        if alert.status == "firing" and deduplication_enabled:
            last_sent_key = f"{alert_name}_sent"
            last_sent_time = alert_history.get(last_sent_key, 0)
            
            if time.time() - last_sent_time < DEDUP_INTERVAL:
                print(f"[MIDDLEWARE] 🔇 ПОВТОР ПОДАВЛЕН: '{alert_name}' (молчание еще {int(DEDUP_INTERVAL - (time.time() - last_sent_time))} сек)")
                repeats_suppressed += 1
                continue
            else:
                alert_history[last_sent_key] = time.time()

        elif alert.status == "resolved":
            alert_history.pop(f"{alert_name}_sent", None)

        # Отправка
        if alert.status == "resolved":
            send_to_gotify(title=f"🟢 РЕШЕНО: {summary}", message="Метрики вернулись в норму.", priority=2)
            delivered += 1
        else:
            priority = 8 if severity == "critical" else 5
            emoji = "🔴" if severity == "critical" else "🟡"
            send_to_gotify(title=f"{emoji} Банк: {summary}", message=alert.annotations.get('description', ''), priority=priority)
            delivered += 1

    return {"status": "ok", "delivered": delivered, "filtered": filtered, "repeats_suppressed": repeats_suppressed}