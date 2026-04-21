from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json

# Enterprise HTML/CSS/JS код
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Управление узлом СПБ-01</title>
    <style>
        :root {
            --bg: #f8f9fb;
            --card-bg: #ffffff;
            --border: #e2e5ea;
            --text-primary: #1a1d21;
            --text-secondary: #5c6370;
            --accent: #0f62fe; /* Корпоративный синий */
            --danger: #da1e28;
            --success: #198038;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-primary);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }
        
        .panel {
            width: 100%;
            max-width: 520px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
            overflow: hidden;
        }

        .panel-header {
            border-bottom: 1px solid var(--border);
            padding: 20px 24px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .node-icon {
            width: 40px; height: 40px;
            background: #f2f4f8;
            border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
            font-size: 20px; color: var(--text-secondary);
        }
        .header-text h1 { font-size: 16px; font-weight: 600; }
        .header-text p { font-size: 12px; color: var(--text-secondary); margin-top: 2px; font-family: monospace; }

        .panel-body { padding: 24px; }
        
        .section-title {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 16px;
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 24px;
        }

        .form-group {
            display: flex;
            flex-direction: column;
        }
        .form-group.full-width { grid-column: span 2; }
        
        .form-group label {
            font-size: 13px;
            font-weight: 500;
            margin-bottom: 6px;
            color: var(--text-primary);
        }
        .form-group select {
            height: 36px;
            padding: 0 12px;
            border: 1px solid var(--border);
            border-radius: 4px;
            background-color: white;
            font-size: 14px;
            color: var(--text-primary);
            cursor: pointer;
            outline: none;
            transition: border-color 0.1s;
        }
        .form-group select:focus { border-color: var(--accent); }

        .actions {
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            padding-top: 16px;
            border-top: 1px solid var(--border);
        }

        button {
            height: 36px;
            padding: 0 20px;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 500;
            border: 1px solid transparent;
            cursor: pointer;
            transition: all 0.1s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .btn-primary {
            background: var(--accent);
            color: white;
        }
        .btn-primary:hover { background: #0043ce; }
        .btn-primary:disabled { background: #a8c7fa; color: white; cursor: not-allowed; }
        
        .btn-secondary {
            background: transparent;
            color: var(--danger);
            border-color: var(--danger);
        }
        .btn-secondary:hover { background: #fff1f1; }
        .btn-secondary:disabled { color: #b0b5bd; border-color: #e2e5ea; background: transparent; cursor: not-allowed; }

        .console-log {
            margin-top: 20px;
            background: #161616;
            border-radius: 4px;
            padding: 12px 16px;
            font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
            font-size: 12px;
            color: #f2f4f8;
            min-height: 40px;
            display: flex;
            align-items: center;
        }
        .console-log.error { color: #ff8389; }
        .console-log.success { color: #42be65; }
        .console-log.wait { color: #8d8d8d; }
        
        .console-prompt {
            color: #525252;
            margin-right: 8px;
            user-select: none;
        }

    </style>
</head>
<body>

<div class="panel">
    <div class="panel-header">
        <div class="node-icon">⬡</div>
        <div class="header-text">
            <h1>Управление узлом</h1>
            <p>server-spb / 10.0.15.2</p>
        </div>
    </div>
    
    <div class="panel-body">
        <div class="section-title">Параметры генерации нагрузки</div>

        <div class="form-row">
            <div class="form-group">
                <label>Целевой CPU</label>
                <select id="cpu">
                    <option value="1">1 ядро (Легкая)</option>
                    <option value="2" selected>2 ядра (Средняя)</option>
                    <option value="4">4 ядра (Высокая)</option>
                </select>
            </div>
            <div class="form-group">
                <label>Целевая RAM</label>
                <select id="memory">
                    <option value="200M">200 МБ</option>
                    <option value="500M" selected>500 МБ</option>
                    <option value="1G">1.0 ГБ</option>
                    <option value="2G">2.0 ГБ</option>
                </select>
            </div>
        </div>

        <div class="form-row">
            <div class="form-group full-width">
                <label>Длительность инцидента</label>
                <select id="duration">
                    <option value="30">30 секунд</option>
                    <option value="60">1 минута</option>
                    <option value="120" selected>2 минуты</option>
                    <option value="300">5 минут</option>
                </select>
            </div>
        </div>

        <div class="actions">
            <button class="btn-secondary" id="stopBtn" onclick="stopLoad()">Прервать</button>
            <button class="btn-primary" id="startBtn" onclick="startLoad()">Применить профиль</button>
        </div>

        <div class="console-log wait" id="consoleOutput">
            <span class="console-prompt">sysmon@spb:</span>
            Ожидание задач...
        </div>
    </div>
</div>

<script>
    const consoleEl = document.getElementById('consoleOutput');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');

    function setConsole(text, type) {
        consoleEl.className = 'console-log ' + type;
        consoleEl.innerHTML = '<span class="console-prompt">sysmon@spb:</span>' + text;
    }

    async function startLoad() {
        startBtn.disabled = true;
        setConsole('Инициализация генератора нагрузки...', 'wait');

        const payload = {
            cpu: document.getElementById('cpu').value,
            memory: document.getElementById('memory').value,
            duration: document.getElementById('duration').value
        };

        try {
            const res = await fetch('/start', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            setConsole(data.message, 'success');
        } catch (e) {
            setConsole('Критическая ошибка сети', 'error');
        } finally {
            startBtn.disabled = false;
        }
    }

    async function stopLoad() {
        stopBtn.disabled = true;
        setConsole('Отправка сигнала SIGKILL процессам...', 'wait');

        try {
            const res = await fetch('/stop', { method: 'POST' });
            const data = await res.json();
            setConsole(data.message, 'success');
        } catch (e) {
            setConsole('Ошибка соединения', 'error');
        } finally {
            stopBtn.disabled = false;
        }
    }
</script>

</body>
</html>
"""

class StressHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode('utf-8'))

    def _send_json(self, message):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({"message": message}, ensure_ascii=False).encode('utf-8'))

    def do_POST(self):
        if self.path == '/start':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data)

            cpu_cores = str(params.get('cpu', '2'))
            mem = str(params.get('memory', '500M'))
            duration = str(params.get('duration', '120'))

            # Защита от дурака
            valid_cpu = ["1", "2", "4"]
            valid_mem = ["200M", "500M", "1G", "2G"]
            if cpu_cores not in valid_cpu: cpu_cores = "2"
            if mem not in valid_mem: mem = "500M"
            try:
                dur_int = int(duration)
                if dur_int > 600: duration = "600"
            except:
                duration = "120"

            # Убиваем старую нагрузку
            subprocess.run(["pkill", "-9", "stress-ng"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Запускаем новую
            subprocess.Popen([
                "stress-ng", 
                "--cpu", cpu_cores, 
                "--io", cpu_cores, 
                "--vm", "1", 
                "--vm-bytes", mem, 
                "--timeout", duration + "s"
            ])

            self._send_json(f"Профиль применен. Генерация запущена (CPU:{cpu_cores}, RAM:{mem}, Timeout:{duration}s).")
            
        elif self.path == '/stop':
            subprocess.run(["pkill", "-9", "stress-ng"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._send_json("Процессы нагрузочного тестирования принудительно завершены.")
            
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), StressHandler)
    print("Web UI запущен на порту 8080")
    server.serve_forever()