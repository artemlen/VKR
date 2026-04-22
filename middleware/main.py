from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import requests
import os
import time
import re
import numpy as np
from datetime import datetime

app = FastAPI(title="Bank Smart AI-Middleware")

GOTIFY_URL = "http://gotify:8080/message"
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN")

alert_history = {}
maintenance_mode = False
deduplication_enabled = True

# Память ML
cpu_history_buffer = []
ML_WINDOW_SIZE = 30

class AlertData(BaseModel):
    status: str
    labels: dict
    annotations: dict

# --- API Управления ---
@app.post("/api/maintenance/on")
async def enable_maintenance():
    global maintenance_mode; maintenance_mode = True
    return {"status": "ok", "message": "Режим обслуживания ВКЛЮЧЕН."}

@app.post("/api/maintenance/off")
async def disable_maintenance():
    global maintenance_mode; maintenance_mode = False
    return {"status": "ok", "message": "Режим обслуживания ВЫКЛЮЧЕН."}

@app.post("/api/dedup/off")
async def disable_dedup():
    global deduplication_enabled; deduplication_enabled = False
    return {"status": "ok", "message": "Дедупликация ВЫКЛЮЧЕНА."}

@app.post("/api/dedup/on")
async def enable_dedup():
    global deduplication_enabled; deduplication_enabled = True
    return {"status": "ok", "message": "Дедупликация ВКЛЮЧЕНА."}

# НОВОЕ: API для сброса памяти ML (ОБЯЗАТЕЛЬНО ДЕЛАТЬ ПЕРЕД ТЕСТАМИ)
@app.post("/api/ml/reset")
async def reset_ml():
    cpu_history_buffer.clear()
    print("[ML ENGINE] 🧹 Буфер очищен. Модель переобучается с нуля.")
    return {"status": "ok", "message": "Память ML сброшена. Начинаем сбор новой статистики."}

def is_business_hours() -> bool:
    now = datetime.now()
    return now.weekday() < 5 and 9 <= now.hour < 18

def check_flapping(alert_name: str, current_status: str) -> dict:
    current_time = time.time()
    FLAP_WINDOW = 180; FLAP_THRESHOLD = 2
    if alert_name not in alert_history:
        alert_history[alert_name] = {"states": [current_status], "last_time": current_time, "is_flapping": False}
        return {"is_flapping": False, "just_started": False}
    history = alert_history[alert_name]
    history["states"] = [s for s in history["states"] if (current_time - history["last_time"]) < FLAP_WINDOW]
    history["states"].append(current_status); history["last_time"] = current_time
    state_changes = sum(1 for i in range(1, len(history["states"])) if history["states"][i] != history["states"][i-1])
    just_started_flapping = False
    if state_changes >= FLAP_THRESHOLD:
        if not history["is_flapping"]: just_started_flapping = True
        history["is_flapping"] = True
    else:
        if history["is_flapping"] and current_status == "resolved":
            history["is_flapping"] = False; history["states"] = []
    return {"is_flapping": history["is_flapping"], "just_started": just_started_flapping}

def send_to_gotify(title: str, message: str, priority: int):
    try:
        requests.post(f"{GOTIFY_URL}?token={GOTIFY_TOKEN}", json={"title": title, "message": message, "priority": priority})
    except Exception as e:
        print(f"[MIDDLEWARE] Ошибка Gotify: {e}")

def parse_cpu_value(text: str) -> float:
    match = re.search(r"(\d+\.\d+)", text)
    return float(match.group(1)) if match else 0.0

def calculate_ml_metrics(current_cpu: float) -> dict:
    cpu_history_buffer.append(current_cpu)
    if len(cpu_history_buffer) > ML_WINDOW_SIZE:
        cpu_history_buffer.pop(0)

    # Холодный старт: если данных мало, не ставим огромный интервал!
    if len(cpu_history_buffer) < 5:
        print(f"[ML ENGINE] ⏳ Холодный старт. Собрано точек: {len(cpu_history_buffer)}/5. Используем стандартный интервал 60с.")
        return {"score": 0, "dynamic_interval": 60, "trend": "⏳ Инициализация", "mean": current_cpu}

    mean_cpu = np.mean(cpu_history_buffer)
    std_cpu = np.std(cpu_history_buffer)
    if std_cpu == 0: std_cpu = 1.0 

    z_score = (current_cpu - mean_cpu) / std_cpu
    anomaly_score = min(100, max(0, (z_score / 3.0) * 100))

    last_val = cpu_history_buffer[-2]
    delta = abs(current_cpu - last_val)
    
    # Ограничиваем интервал: от 60 сек (экстренно) до 180 сек (максимум для демо, чтобы не ждать 10 минут)
    dynamic_interval = int(max(60, min(180, 600 - (delta * 30))))

    if current_cpu > cpu_history_buffer[-5]: trend = "📈 Резкий рост"
    elif current_cpu < cpu_history_buffer[-5]: trend = "📉 Спад"
    else: trend = "➡️ Плато"

    # ВЫВОДИМ ВСЮ МАТЕМАТИКУ В ТЕРМИНАЛ!
    print(f"[ML ENGINE] 🧠 CPU: {current_cpu}% | Норма: {mean_cpu:.1f}% | Отклонение (Z): {z_score:.1f} | Аномалия: {anomaly_score:.0f}% | Delta: {delta:.1f} | Интервал: {dynamic_interval}с | {trend}")

    return {
        "score": round(anomaly_score, 1),
        "dynamic_interval": dynamic_interval,
        "trend": trend,
        "mean": round(mean_cpu, 1)
    }

@app.post("/alert")
async def handle_alert(request: Request):
    if not GOTIFY_TOKEN or GOTIFY_TOKEN == "YOUR_TOKEN_HERE":
        raise HTTPException(status_code=500, detail="Gotify token error")

    body = await request.json()
    alerts = body.get("alerts", [])
    delivered = 0; filtered = 0; repeats_suppressed = 0

    for alert_data in alerts:
        alert = AlertData(status=alert_data.get("status"), labels=alert_data.get("labels", {}), annotations=alert_data.get("annotations", {}))
        alert_name = alert.labels.get("alertname", "Unknown")
        severity = alert.labels.get("severity", "info")
        summary = alert.annotations.get("summary", alert_name)
        description = alert.annotations.get("description", "")

        if maintenance_mode and severity != "critical":
            print(f"[MIDDLEWARE] 🔧 ОБСЛУЖИВАНИЕ: '{alert_name}' проигнорирован."); filtered += 1; continue
        if not is_business_hours() and severity == "warning":
            print(f"[MIDDLEWARE] 🌙 НОЧНОЙ РЕЖИМ: '{alert_name}' отложен."); filtered += 1; continue

        flap_info = check_flapping(alert_name, alert.status)
        if flap_info["is_flapping"]:
            if flap_info["just_started"]:
                send_to_gotify(title=f"⚠️ FLAPPING: {summary}", message="Обнаружен хаотичный сдвиг статуса.", priority=6); delivered += 1
            else: filtered += 1
            continue

        current_interval = 300 
        ml_info_text = ""
        
        if alert.status == "firing":
            if "CPU" in alert_name:
                current_cpu = parse_cpu_value(description)
                ml_data = calculate_ml_metrics(current_cpu)
                current_interval = ml_data["dynamic_interval"]
                
                ml_info_text = (f"\n\n🧠 [ML Аналитика]\n"
                                 f"Уверенность: {ml_data['score']}% | Тренд: {ml_data['trend']}\n"
                                 f"Фоновая норма: {ml_data['mean']}% | Динам. интервал повтора: {current_interval}с")

            if deduplication_enabled:
                last_sent_key = f"{alert_name}_sent"
                last_sent_time = alert_history.get(last_sent_key, 0)
                
                if time.time() - last_sent_time < current_interval:
                    print(f"[MIDDLEWARE] 🔇 ML ПОДАВИЛ ПОВТОР: '{alert_name}'. Осталось молчать {int(current_interval - (time.time() - last_sent_time))}с.")
                    repeats_suppressed += 1; continue
                else:
                    alert_history[last_sent_key] = time.time()

        elif alert.status == "resolved":
            alert_history.pop(f"{alert_name}_sent", None)

        if alert.status == "resolved":
            send_to_gotify(title=f"🟢 РЕШЕНО: {summary}", message="Метрики вернулись в норму.", priority=2); delivered += 1
        else:
            priority = 8 if severity == "critical" else 5
            emoji = "🔴" if severity == "critical" else "🟡"
            send_to_gotify(title=f"{emoji} Банк: {summary}", message=description + ml_info_text, priority=priority)
            delivered += 1

    return {"status": "ok", "delivered": delivered, "filtered": filtered, "repeats_suppressed": repeats_suppressed}