FROM alpine:latest

# Устанавливаем stress-ng для генерации нагрузки и bash для удобства
RUN apk add --no-cache bash stress-ng

# Скачиваем node_exporter для ARM64 (Mac M1)
RUN wget -q https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-arm64.tar.gz \
    && tar xzf node_exporter-1.7.0.linux-arm64.tar.gz \
    && mv node_exporter-1.7.0.linux-arm64/node_exporter /usr/local/bin/ \
    && rm -rf node_exporter-1.7.0.linux-arm64*

# Запускаем экспортер в фоне и держим контейнер живым
CMD node_exporter --web.listen-address=:9100 & tail -f /dev/null