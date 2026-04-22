from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json

# Enterprise HTML/CSS/JS код со слайдерами
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
            --accent: #0f62fe;
            --accent-light: #d0e2ff;
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
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            overflow: hidden;
        }

        .panel-header {
            border-bottom: 1px solid var(--border);
            padding: 24px;
            display: flex;
            align-items: center;
            gap: 16px;
            background: linear-gradient(to right, #fafbfc, #f4f7f6);
        }
        .node-icon {
            width: 44px; height: 44px;
            background: var(--accent-light);
            color: var(--accent);
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px; font-weight: bold;
        }
        .header-text h1 { font-size: 17px; font-weight: 600; }
        .header-text p { font-size: 12px; color: var(--text-secondary); margin-top: 3px; font-family: monospace; }

        .panel-body { padding: 28px; }
        
        .section-title {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 24px;
        }

        .control-group {
            margin-bottom: 28px;
        }
        .control-label {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .control-label label {
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
        }
        .control-value {
            font-size: 13px;
            font-weight: 600;
            color: var(--accent);
            background: var(--accent-light);
            padding: 3px 8px;
            border-radius: 4px;
        }

        /* Красивые слайдеры */
        input[type="range"] {
            -webkit-appearance: none;
            appearance: none;
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: var(--border);
            outline: none;
            cursor: pointer;
        }
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--accent);
            border: 3px solid white;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            transition: transform 0.15s ease;
        }
        input[type="range"]::-webkit-slider-thumb:hover {
            transform: scale(1.15);
        }
        input[type="range"]::-moz-range-thumb {
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: var(--accent);
            border: 3px solid white;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            cursor: pointer;
        }

        .actions {
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
        }

        button {
            height: 40px;
            padding: 0 24px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            border: 1px solid transparent;
            cursor: pointer;
            transition: all 0.15s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .btn-primary {
            background: var(--accent);
            color: white;
            box-shadow: 0 2px 0 #0043ce;
        }
        .btn-primary:hover { background: #0043ce; }
        .btn-primary:active { transform: translateY(1px); box-shadow: none; }
        .btn-primary:disabled { background: #a8c7fa; color: white; cursor: not-allowed; box-shadow: none; }
        
        .btn-secondary {
            background: transparent;
            color: var(--danger);
            border-color: var(--danger);
        }
        .btn-secondary:hover { background: #fff1f1; }
        .btn-secondary:disabled { color: #b0b5bd; border-color: #e2e5ea; background: transparent; cursor: not-allowed; }

        .console-log {
            margin-top: 24px;
            background: #161616;
            border-radius: 6px;
            padding: 14px 18px;
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 12px;
            color: #f2f4f8;
            min-height: 44px;
            display: flex;
            align-items: center;
        }
        .console-log.error { color: #ff8389; }
        .console-log.success { color: #42be65; }
        .console-log.wait { color: #8d8d8d; }
        .console-prompt { color: #525252; margin-right: 8px; user-select: none; }
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
        <div class="section-title">Профиль генерации нагрузки</div>

        <div class="control-group">
            <div class="control-label">
                <label>Целевой CPU</label>
                <span class="control-value" id="cpuVal">2 ядра</span>
            </div>
            <input type="range" id="cpu" min="1" max="8" value="2" oninput="updateUI()">
            <div style="display:flex; justify-content:space-between; font-size:10px; color:#8d8d8d; margin-top:4px;">
                <span>1 ядро</span>
                <span>8 ядер</span>
            </div>
        </div>

        <div class="control-group">
            <div class="control-label">
                <label>Целевая RAM</label>
                <span class="control-value" id="ramVal">500 МБ</span>
            </div>
            <input type="range" id="memory" min="100" max="4096" step="100" value="500" oninput="updateUI()">
            <div style="display:flex; justify-content:space-between; font-size:10px; color:#8d8d8d; margin-top:4px;">
                <span>100 МБ</span>
                <span>4 ГБ</span>
            </div>
        </div>

        <div class="control-group">
            <div class="control-label">
                <label>Длительность инцидента</label>
                <span class="control-value" id="durationVal">2 мин</span>
            </div>
            <input type="range" id="duration" min="10" max="300" step="10" value="120" oninput="updateUI()">
            <div style="display:flex; justify-content:space-between; font-size:10px; color:#8d8d8d; margin-top:4px;">
                <span>10 сек</span>
                <span>5 мин</span>
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
    function updateUI() {
        const cpu = document.getElementById('cpu').value;
        const ram = document.getElementById('memory').value;
        const dur = document.getElementById('duration').value;

        // Форматируем текст для CPU
        let cpuText = cpu + ' ядер';
        if (cpu == 1) cpuText = '1 ядро';
        else if (cpu >= 2 && cpu <= 4) cpuText = cpu + ' ядра';
        document.getElementById('cpuVal').innerText = cpuText;

        // Форматируем текст для RAM
        let ramText = ram >= 1024 ? (ram / 1024) + ' ГБ' : ram + ' МБ';
        document.getElementById('ramVal').innerText = ramText;

        // Форматируем текст для времени
        let durText = dur + ' сек';
        if (dur >= 60) {
            const m = Math.floor(dur / 60);
            const s = dur % 60;
            durText = s > 0 ? m + ' мин ' + s + ' сек' : m + ' мин';
        }
        document.getElementById('durationVal').innerText = durText;
    }

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
            memory_mb: document.getElementById('memory').value, // Отправляем просто число (например, 1024)
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

            # 1. Получаем сырые числа со слайдеров
            cpu_raw = params.get('cpu', '2')
            memory_raw = int(params.get('memory_mb', 500))
            duration_raw = str(params.get('duration', '120'))

            # 2. Валидация и форматирование CPU
            try:
                cpu_cores = str(max(1, min(8, int(cpu_raw))))
            except:
                cpu_cores = "2"

            # 3. Умная конвертация RAM для stress-ng (переводим МБ в формат 500m или 1g)
            try:
                memory_raw = max(100, min(4096, memory_raw))
                if memory_raw >= 1024:
                    ram_str = f"{memory_raw // 1024}g"
                else:
                    ram_str = f"{memory_raw}m"
            except:
                ram_str = "500m"

            # 4. Валидация времени
            try:
                dur_int = int(duration_raw)
                if dur_int > 600: duration = "600"
                elif dur_int < 10: duration = "10"
                else: duration = str(dur_int)
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
                "--vm-bytes", ram_str, 
                "--timeout", duration + "s"
            ])

            self._send_json(f"Профиль применен. CPU: {cpu_cores} ядер, RAM: {ram_str}, Таймаут: {duration}с.")
            
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