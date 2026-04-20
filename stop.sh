#!/usr/bin/env bash
echo "Остановка системы мониторинга..."

if docker compose version >/dev/null 2>&1; then
  docker compose down
else
  docker-compose down
fi

echo "✓ Система остановлена"