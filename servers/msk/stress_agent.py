"""
Stress Agent — запускается внутри контейнера сервера.
Принимает команды по HTTP и запускает реальную нагрузку.
"""
import threading
import time
import math
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

stop_events = []
active_threads = []
lock = threading.Lock()
status = {"active": False, "type": None, "intensity": 0}


def cpu_worker(stop_event, intensity):
    cycle = 0.1
    work_time = cycle * (intensity / 100.0)
    sleep_time = cycle * (1 - intensity / 100.0)
    while not stop_event.is_set():
        start = time.perf_counter()
        while time.perf_counter() - start < work_time:
            _ = math.sqrt(sum(i * i for i in range(1000)))
        time.sleep(max(sleep_time, 0.001))


def memory_worker(stop_event, intensity):
    mb = int(64 + (intensity / 100.0) * 448)
    chunk = bytearray(mb * 1024 * 1024)
    idx = 0
    while not stop_event.is_set():
        chunk[idx % len(chunk)] = idx % 256
        idx += 1
        if idx % 100000 == 0:
            time.sleep(0.01)
    del chunk


def stop_all():
    global stop_events, active_threads
    with lock:
        for e in stop_events:
            e.set()
        stop_events = []
        active_threads = []
        status["active"] = False
        status["type"] = None
        status["intensity"] = 0


def start_load(load_type, intensity, duration):
    stop_all()
    time.sleep(0.2)

    new_stop_events = []
    threads = []

    if load_type in ("cpu", "mixed"):
        cpu_int = intensity if load_type == "cpu" else intensity // 2
        num_cores = max(1, os.cpu_count() or 1)
        for _ in range(num_cores):
            e = threading.Event()
            t = threading.Thread(target=cpu_worker, args=(e, cpu_int), daemon=True)
            t.start()
            new_stop_events.append(e)
            threads.append(t)

    if load_type in ("memory", "mixed"):
        mem_int = intensity if load_type == "memory" else intensity // 2
        e = threading.Event()
        t = threading.Thread(target=memory_worker, args=(e, mem_int), daemon=True)
        t.start()
        new_stop_events.append(e)
        threads.append(t)

    with lock:
        stop_events.extend(new_stop_events)
        active_threads.extend(threads)
        status["active"] = True
        status["type"] = load_type
        status["intensity"] = intensity

    if duration > 0:
        def auto_stop():
            time.sleep(duration)
            stop_all()
        threading.Thread(target=auto_stop, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # подавляем лишние логи

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        if self.path == "/start":
            start_load(
                data.get("load_type", "cpu"),
                data.get("intensity", 50),
                data.get("duration", 60),
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode())

        elif self.path == "/stop":
            stop_all()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stopped"}).encode())

        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            with lock:
                self.wfile.write(json.dumps(status).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("AGENT_PORT", 9200))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Stress Agent запущен на порту {port}")
    server.serve_forever()