"""
Load Generator — управляет нагрузкой через HTTP-агенты внутри серверов.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("load-generator")

app = FastAPI(title="Load Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Адреса агентов внутри docker-сети
AGENTS = {
    "msk": "http://server-msk:9200",
    "spb": "http://server-spb:9200",
}

# Отслеживание активных задач
active_loads: dict[str, dict] = {}


class LoadRequest(BaseModel):
    target: str
    load_type: str = "cpu"
    intensity: int = 50
    duration: int = 60


class StopRequest(BaseModel):
    target: str


async def send_to_agent(target: str, path: str, payload: Optional[dict] = None) -> dict:
    """Отправляет команду агенту внутри контейнера."""
    url = AGENTS.get(target)
    if not url:
        raise HTTPException(status_code=400, detail=f"Неизвестный target: {target}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if payload is not None:
                resp = await client.post(f"{url}{path}", json=payload)
            else:
                resp = await client.get(f"{url}{path}")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Агент {target} недоступен. Проверьте что контейнер запущен."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load/start")
async def start_load(req: LoadRequest):
    targets = ["msk", "spb"] if req.target == "both" else [req.target]
    
    if req.target not in ("msk", "spb", "both"):
        raise HTTPException(status_code=400, detail="target: msk | spb | both")
    if req.load_type not in ("cpu", "memory", "mixed"):
        raise HTTPException(status_code=400, detail="load_type: cpu | memory | mixed")
    if not (1 <= req.intensity <= 100):
        raise HTTPException(status_code=400, detail="intensity: 1–100")

    results = {}
    for target in targets:
        result = await send_to_agent(target, "/start", {
            "load_type": req.load_type,
            "intensity": req.intensity,
            "duration": req.duration,
        })
        active_loads[target] = {
            "type": req.load_type,
            "intensity": req.intensity,
            "duration": req.duration,
            "started_at": time.time(),
        }
        results[target] = result
        log.info(f"Нагрузка запущена на {target}: {req.load_type} @ {req.intensity}%")

    return {
        "status": "started",
        "targets": targets,
        "load_type": req.load_type,
        "intensity": req.intensity,
        "duration": req.duration,
        "results": results,
    }


@app.post("/load/stop")
async def stop_load(req: StopRequest):
    targets = ["msk", "spb"] if req.target == "both" else [req.target]
    
    results = {}
    for target in targets:
        result = await send_to_agent(target, "/stop", {})
        active_loads.pop(target, None)
        results[target] = result
        log.info(f"Нагрузка остановлена на {target}")

    return {"status": "stopped", "targets": targets, "results": results}


@app.get("/load/status")
async def load_status():
    status = {}
    for target, agent_url in AGENTS.items():
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{agent_url}/status")
                status[target] = resp.json()
        except Exception:
            status[target] = {"active": False, "error": "агент недоступен"}

    return {"servers": status, "total_active": sum(1 for s in status.values() if s.get("active"))}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(content=_get_ui_html())


def _get_ui_html() -> str:
    return """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Load Generator — Bank Monitoring</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 2rem;
  }
  h1 { color: #60a5fa; margin-bottom: 0.5rem; font-size: 1.8rem; }
  .subtitle { color: #94a3b8; margin-bottom: 2rem; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  .card {
    background: #1e2433; border: 1px solid #2d3748;
    border-radius: 12px; padding: 1.5rem;
  }
  .card h2 { color: #93c5fd; margin-bottom: 1rem; font-size: 1.1rem; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
  .badge-msk { background: #1e3a5f; color: #60a5fa; }
  .badge-spb { background: #1a3c2f; color: #34d399; }
  label { display: block; color: #94a3b8; font-size: 0.875rem; margin-bottom: 0.4rem; margin-top: 0.8rem; }
  select, input[type=range], input[type=number] {
    width: 100%; background: #2d3748; border: 1px solid #4a5568;
    color: #e2e8f0; border-radius: 6px; padding: 0.5rem; font-size: 0.875rem;
  }
  .btn {
    display: inline-block; padding: 0.6rem 1.4rem; border-radius: 8px;
    border: none; font-size: 0.875rem; font-weight: 600;
    cursor: pointer; transition: opacity 0.2s; margin-top: 1rem;
  }
  .btn:hover { opacity: 0.85; }
  .btn-start { background: #3b82f6; color: white; }
  .btn-stop  { background: #ef4444; color: white; }
  .btns { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  #status-box {
    background: #111827; border-radius: 8px; padding: 1rem;
    font-family: monospace; font-size: 0.8rem; color: #94a3b8;
    min-height: 120px; white-space: pre-wrap; max-height: 300px; overflow-y: auto;
  }
  .full-width { grid-column: 1 / -1; }
  .quick-btns { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .btn-quick { background: #374151; color: #d1d5db; font-size: 0.8rem; padding: 0.4rem 0.9rem; border: none; border-radius: 6px; cursor: pointer; }
  .btn-quick:hover { background: #4b5563; }
</style>
</head>
<body>
<h1>⚡ Load Generator</h1>
<p class="subtitle">Симулятор нагрузки — нагружает реальные контейнеры MSK и SPB</p>

<div class="grid">
  <div class="card">
    <h2><span class="badge badge-msk">MSK</span> &nbsp;Москва</h2>
    <label>Тип нагрузки</label>
    <select id="msk-type">
      <option value="cpu">CPU</option>
      <option value="memory">Memory</option>
      <option value="mixed">Mixed</option>
    </select>
    <label>Интенсивность: <span id="msk-int-val">80</span>%</label>
    <input type="range" id="msk-intensity" min="1" max="100" value="80"
      oninput="document.getElementById('msk-int-val').textContent=this.value">
    <label>Длительность (сек, 0 = ∞)</label>
    <input type="number" id="msk-duration" value="60" min="0" max="3600">
    <div class="btns">
      <button class="btn btn-start" onclick="startLoad('msk')">▶ Запустить MSK</button>
      <button class="btn btn-stop"  onclick="stopLoad('msk')">⏹ Стоп MSK</button>
    </div>
  </div>

  <div class="card">
    <h2><span class="badge badge-spb">SPB</span> &nbsp;Санкт-Петербург</h2>
    <label>Тип нагрузки</label>
    <select id="spb-type">
      <option value="cpu">CPU</option>
      <option value="memory">Memory</option>
      <option value="mixed">Mixed</option>
    </select>
    <label>Интенсивность: <span id="spb-int-val">80</span>%</label>
    <input type="range" id="spb-intensity" min="1" max="100" value="80"
      oninput="document.getElementById('spb-int-val').textContent=this.value">
    <label>Длительность (сек, 0 = ∞)</label>
    <input type="number" id="spb-duration" value="60" min="0" max="3600">
    <div class="btns">
      <button class="btn btn-start" onclick="startLoad('spb')">▶ Запустить SPB</button>
      <button class="btn btn-stop"  onclick="stopLoad('spb')">⏹ Стоп SPB</button>
    </div>
  </div>

  <div class="card full-width">
    <h2>🚀 Быстрые сценарии</h2>
    <div class="quick-btns">
      <button class="btn-quick" onclick="scenario('cpu_spike_msk')">💥 CPU Spike MSK (90%, 30s)</button>
      <button class="btn-quick" onclick="scenario('cpu_spike_spb')">💥 CPU Spike SPB (90%, 30s)</button>
      <button class="btn-quick" onclick="scenario('cpu_both')">💥 CPU Both (85%, 45s)</button>
      <button class="btn-quick" onclick="scenario('mem_msk')">🧠 Memory MSK (85%, 60s)</button>
      <button class="btn-quick" onclick="scenario('mem_spb')">🧠 Memory SPB (85%, 60s)</button>
      <button class="btn-quick" onclick="scenario('mixed_both')">🌪 Mixed Both (75%, 60s)</button>
      <button class="btn btn-stop" style="margin-top:0" onclick="stopAll()">⏹ Стоп ALL</button>
    </div>
  </div>

  <div class="card full-width">
    <h2>📊 Статус серверов</h2>
    <div id="status-box">Загрузка...</div>
    <div class="btns">
      <button class="btn-quick" style="margin-top:0.75rem" onclick="refreshStatus()">🔄 Обновить</button>
    </div>
  </div>
</div>

<script>
const SCENARIOS = {
  cpu_spike_msk: {target:'msk',  load_type:'cpu',    intensity:90, duration:30},
  cpu_spike_spb: {target:'spb',  load_type:'cpu',    intensity:90, duration:30},
  cpu_both:      {target:'both', load_type:'cpu',    intensity:85, duration:45},
  mem_msk:       {target:'msk',  load_type:'memory', intensity:85, duration:60},
  mem_spb:       {target:'spb',  load_type:'memory', intensity:85, duration:60},
  mixed_both:    {target:'both', load_type:'mixed',  intensity:75, duration:60},
};

async function post(path, body) {
  const r = await fetch(path, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
  });
  return r.json();
}

async function startLoad(target) {
  const type     = document.getElementById(target+'-type').value;
  const intensity = parseInt(document.getElementById(target+'-intensity').value);
  const duration  = parseInt(document.getElementById(target+'-duration').value);
  const res = await post('/load/start', {target, load_type:type, intensity, duration});
  document.getElementById('status-box').textContent = JSON.stringify(res, null, 2);
  setTimeout(refreshStatus, 1000);
}

async function stopLoad(target) {
  const res = await post('/load/stop', {target});
  document.getElementById('status-box').textContent = JSON.stringify(res, null, 2);
  setTimeout(refreshStatus, 500);
}

async function stopAll() {
  const res = await post('/load/stop', {target:'both'});
  document.getElementById('status-box').textContent = JSON.stringify(res, null, 2);
  setTimeout(refreshStatus, 500);
}

async function scenario(name) {
  const cfg = SCENARIOS[name];
  const res = await post('/load/start', cfg);
  document.getElementById('status-box').textContent =
    'Сценарий: ' + name + '\n' + JSON.stringify(res, null, 2);
  setTimeout(refreshStatus, 1000);
}

async function refreshStatus() {
  try {
    const r = await fetch('/load/status');
    const data = await r.json();
    document.getElementById('status-box').textContent = JSON.stringify(data, null, 2);
  } catch(e) {
    document.getElementById('status-box').textContent = 'Ошибка: ' + e.message;
  }
}

refreshStatus();
setInterval(refreshStatus, 4000);
</script>
</body>
</html>"""