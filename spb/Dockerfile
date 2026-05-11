FROM alpine:latest

# Устанавливаем stress-ng, bash, python3 (для веб-интерфейса) и утилиты для проверки процессов
RUN apk add --no-cache bash stress-ng python3 procps

# Скачиваем node_exporter для ARM64 
RUN wget -q https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-arm64.tar.gz \
    && tar xzf node_exporter-1.7.0.linux-arm64.tar.gz \
    && mv node_exporter-1.7.0.linux-arm64/node_exporter /usr/local/bin/ \
    && rm -rf node_exporter-1.7.0.linux-arm64*

# Копируем скрипт веб-интерфейса внутрь контейнера
COPY stress_api.py /app/stress_api.py

# Запускаем экспортер метрик, запускаем веб-сервер и держим контейнер живым
CMD node_exporter --web.listen-address=:9100 & python3 /app/stress_api.py & tail -f /dev/null