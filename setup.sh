#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[→]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║   Bank Infrastructure Monitoring System        ║"
echo "║   Setup Script                                 ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# ── Проверки ──────────────────────────────────────────────────────────────────
info "Проверка зависимостей..."

command -v docker >/dev/null 2>&1 || { err "Docker не установлен!"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || \
  docker compose version >/dev/null 2>&1 || \
  { err "Docker Compose не установлен!"; exit 1; }

log "Docker: $(docker --version)"

# ── Определяем команду compose ────────────────────────────────────────────────
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
else
  COMPOSE="docker-compose"
fi

# ── Сборка и запуск ───────────────────────────────────────────────────────────
info "Сборка образов..."
$COMPOSE build --no-cache

info "Запуск сервисов..."
$COMPOSE up -d

info "Ожидание запуска сервисов (30 секунд)..."
sleep 30

# ── Настройка Gotify ──────────────────────────────────────────────────────────
info "Настройка Gotify..."

GOTIFY_URL="http://localhost:8080"
MAX_RETRIES=10
RETRY=0

while [ $RETRY -lt $MAX_RETRIES ]; do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$GOTIFY_URL/health" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    log "Gotify доступен"
    break
  fi
  RETRY=$((RETRY + 1))
  warn "Gotify не готов (попытка $RETRY/$MAX_RETRIES)..."
  sleep 5
done

if [ $RETRY -eq $MAX_RETRIES ]; then
  err "Gotify недоступен после $MAX_RETRIES попыток"
  err "Проверьте: docker logs gotify"
  exit 1
fi

# Создаём приложение в Gotify
info "Создание приложения в Gotify..."
APP_RESPONSE=$(curl -s -X POST "$GOTIFY_URL/application" \
  -H "Content-Type: application/json" \
  -u "admin:admin123" \
  -d '{"name":"Bank Monitoring","description":"Алерты банковской инфраструктуры"}')

GOTIFY_TOKEN=$(echo "$APP_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")

if [ -z "$GOTIFY_TOKEN" ]; then
  warn "Не удалось автоматически получить токен Gotify"
  warn "Получите токен вручную:"
  warn "  1. Откройте http://localhost:8080"
  warn "  2. Войдите: admin / admin123"
  warn "  3. Apps → Create Application"
  warn "  4. Скопируйте токен"
  warn "  5. Выполните: GOTIFY_TOKEN=<ваш_токен> ./setup.sh --update-token"
else
  log "Gotify токен получен: $GOTIFY_TOKEN"

  # Обновляем токен в middleware
  info "Обновление токена в middleware..."
  $COMPOSE stop middleware
  GOTIFY_TOKEN="$GOTIFY_TOKEN" $COMPOSE up -d middleware

  # Ждём перезапуска
  sleep 5

  # Обновляем docker-compose.yml
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/GOTIFY_TOKEN=PLACEHOLDER/GOTIFY_TOKEN=$GOTIFY_TOKEN/" docker-compose.yml
  else
    sed -i "s/GOTIFY_TOKEN=PLACEHOLDER/GOTIFY_TOKEN=$GOTIFY_TOKEN/" docker-compose.yml
  fi

  log "Токен обновлён в docker-compose.yml"
fi

# ── Проверка сервисов ─────────────────────────────────────────────────────────
echo ""
info "Проверка состояния сервисов..."
echo ""

check_service() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
  if [ "$code" = "200" ] || [ "$code" = "302" ]; then
    log "$name — OK ($url)"
  else
    warn "$name — HTTP $code ($url)"
  fi
}

check_service "Prometheus"     "http://localhost:9090/-/healthy"
check_service "Grafana"        "http://localhost:3000/api/health"
check_service "Gotify"         "http://localhost:8080/health"
check_service "Middleware"     "http://localhost:8081/health"
check_service "Load Generator" "http://localhost:8082/health"
check_service "Node MSK"       "http://localhost:9101/metrics"
check_service "Node SPB"       "http://localhost:9102/metrics"

# ── Тестовое уведомление ──────────────────────────────────────────────────────
if [ -n "$GOTIFY_TOKEN" ]; then
  info "Отправка тестового уведомления..."
  TEST_RESP=$(curl -s -X POST "http://localhost:8081/send" \
    -H "Content-Type: application/json" \
    -d '{"title":"🚀 Система мониторинга запущена","message":"Bank Infrastructure Monitoring успешно развёрнут.\n\nСерверы MSK и SPB в сети.\nGrafana и Prometheus готовы к работе.","priority":5}')
  log "Тестовое уведомление: $TEST_RESP"
fi

# ── Итог ──────────────────────────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    Система запущена! 🎉                   ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Grafana:        http://localhost:3000  (admin/admin123)   ║"
echo "║  Prometheus:     http://localhost:9090                      ║"
echo "║  Gotify:         http://localhost:8080  (admin/admin123)   ║"
echo "║  Middleware:     http://localhost:8081                      ║"
echo "║  Middleware API: http://localhost:8081/docs                 ║"
echo "║  Load Generator: http://localhost:8082                      ║"
echo "║  Node MSK:       http://localhost:9101/metrics              ║"
echo "║  Node SPB:       http://localhost:9102/metrics              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

if [ -n "$GOTIFY_TOKEN" ]; then
  echo -e "  ${GREEN}Gotify Token:${NC} $GOTIFY_TOKEN"
  echo ""
fi

echo "  Управление:"
echo "  • Остановить: docker compose down"
echo "  • Логи:       docker compose logs -f <service>"
echo "  • Нагрузка:   http://localhost:8082"
echo ""