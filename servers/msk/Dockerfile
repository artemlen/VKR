FROM alpine:3.18

# Устанавливаем все зависимости включая stress-ng
RUN apk update && apk add --no-cache \
    curl \
    bash \
    wget \
    python3 \
    stress-ng \
    procps

# Проверяем что stress-ng установился
RUN stress-ng --version

# Скачиваем node_exporter
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        NE_ARCH="arm64"; \
    else \
        NE_ARCH="amd64"; \
    fi && \
    wget -q "https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-${NE_ARCH}.tar.gz" \
         -O /tmp/node_exporter.tar.gz && \
    tar xzf /tmp/node_exporter.tar.gz -C /tmp && \
    mv /tmp/node_exporter-1.6.1.linux-${NE_ARCH}/node_exporter /usr/local/bin/ && \
    rm -rf /tmp/node_exporter*

# Копируем агент
COPY stress_agent.py /app/stress_agent.py

# Скрипт запуска
RUN printf '#!/bin/sh\n\
python3 /app/stress_agent.py &\n\
exec /usr/local/bin/node_exporter \\\n\
  --collector.disable-defaults \\\n\
  --collector.cpu \\\n\
  --collector.meminfo \\\n\
  --collector.loadavg \\\n\
  --collector.filesystem \\\n\
  --collector.netdev \\\n\
  --collector.stat \\\n\
  --collector.time \\\n\
  --collector.uname \\\n\
  --web.listen-address=:9100\n' > /start.sh && chmod +x /start.sh

EXPOSE 9100 9200

CMD ["/start.sh"]