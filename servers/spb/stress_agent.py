"""
Stress Agent — использует stress-ng для реальной нагрузки на контейнер.
"""
import subprocess
import os
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Текущий процесс stress-ng
current_process = None
process_lock = threading.Lock()
current_status = {"active": False, "type": None, "intensity": 0}


def stop_stress():
    """Останавливает текущую нагрузку."""
    global current_process, current_status
    with process_lock:
        if current_process is not None:
            try:
                # Убиваем процесс и все дочерние
                os.killpg(os.getpgid(current_process.pid), signal.SIGTERM)
            except Exception as e:
                print(f"Ошибка при остановке: {e}")
                try:
                    current_process.kill()
                except Exception:
                    pass
            current_process = None
        current_status = {"active": False, "type": None, "intensity": 0}


def start_stress(load_type: str, intensity: int, duration: int):
    """Запускает stress-ng с заданными параметрами."""
    global current_process, current_status

    # Сначала останавливаем предыдущую нагрузку
    stop_stress()

    num_cpus = os.cpu_count() or 1

    # Формируем команду stress-ng
    cmd = ["stress-ng"]

    if load_type == "cpu":
        cmd += [
            "--cpu", str(num_cpus),
            "--cpu-load", str(intensity),
        ]
    elif load_type == "memory":
        # Выделяем память пропорционально интенсивности
        mem_mb = int(64 + (intensity / 100.0) * 256)
        cmd += [
            "--vm", "1",
            "--vm-bytes", f"{mem_mb}M",
            "--vm-keep",
        ]
    elif load_type == "mixed":
        mem_mb = int(64 + (intensity / 100.0) * 128)
        cmd += [
            "--cpu", str(num_cpus),
            "--cpu-load", str(intensity // 2),
            "--vm", "1",
            "--vm-bytes", f"{mem_mb}M",
            "--vm-keep",
        ]

    # Длительность
    if duration > 0:
        cmd += ["--timeout", str(duration)]

    cmd += ["--metrics-brief"]

    print(f"Запуск команды: {' '.join(cmd)}")

    with process_lock:
        try:
            current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,  # создаём новую группу процессов
            )
            current_status = {
                "active": True,
                "type": load_type,
                "intensity": intensity,
                "duration": duration,
                "pid": current_process.pid,
            }
            print(f"stress-ng запущен PID={current_process.pid}")
        except Exception as e:
            print(f"Ошибка запуска stress-ng: {e}")
            current_status = {"active": False, "type": None, "intensity": 0}
            return

    # Автостоп через duration секунд
    if duration > 0:
        def auto_stop():
            import time
            time.sleep(duration + 2)
            with process_lock:
                global current_process
                if current_process is not None:
                    try:
                        poll = current_process.poll()
                        if poll is None:
                            stop_stress()
                    except Exception:
                        pass
            current_status["active"] = False
        threading.Thread(target=auto_stop, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # подавляем HTTP логи

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)

        try:
            data = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "invalid json"}')
            return

        if self.path == "/start":
            load_type = data.get("load_type", "cpu")
            intensity = int(data.get("intensity", 50))
            duration = int(data.get("duration", 60))

            # Запускаем в отдельном потоке чтобы не блокировать HTTP
            threading.Thread(
                target=start_stress,
                args=(load_type, intensity, duration),
                daemon=True,
            ).start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "started",
                "load_type": load_type,
                "intensity": intensity,
                "duration": duration,
            }).encode())

        elif self.path == "/stop":
            threading.Thread(target=stop_stress, daemon=True).start()

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
            with process_lock:
                # Проверяем реальный статус процесса
                if current_process is not None:
                    poll = current_process.poll()
                    if poll is not None:
                        # Процесс завершился
                        current_status["active"] = False
                self.wfile.write(json.dumps(current_status).encode())

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
    print(f"Stress Agent запущен на порту {port}")
    print(f"CPUs доступно: {os.cpu_count()}")
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()