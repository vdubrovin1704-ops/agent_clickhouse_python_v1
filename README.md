# ClickHouse + Python Analysis Agent

Единый агент, который получает запрос пользователя, выгружает данные из ClickHouse в Parquet, анализирует их Python-кодом (pandas + matplotlib/seaborn) и возвращает текст, таблицы и графики. Реализован через Anthropic Messages API с native tool-use.

## Быстрый старт (Ubuntu)
1. Склонируйте репозиторий и перейдите в корень проекта.
2. Подготовьте окружение:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
3. Заполните `.env` (пример в `.env.example`). Для работы нужны Anthropic API ключ и доступ к ClickHouse. При необходимости скачайте сертификат Яндекс Cloud (делает `setup.sh`).
4. Протестируйте агента без API:
   ```bash
   source venv/bin/activate
   python local_test.py --query "Покажи топ-5 записей из таблицы sales"
   ```
   Скрипт выведет текстовый ответ, количество графиков и лог вызовов tools.
5. (Опционально) Запустите REST API:
   ```bash
   source venv/bin/activate
   uvicorn api_server:app --host 0.0.0.0 --port 8000
   ```

## Конфигурация
- `.env` — ключи Anthropic и параметры ClickHouse (`CLICKHOUSE_HOST`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`, `CLICKHOUSE_SSL_CERT_PATH`).
- Parquet и временные данные сохраняются в `temp_data/`, история чатов — `chat_history.db`.
- Основные файлы:
  - `config.py` — загрузка конфигурации
  - `clickhouse_client.py` — запросы к ClickHouse и сохранение в Parquet
  - `python_sandbox.py` — выполнение Python-кода с захватом графиков
  - `chat_storage.py` — SQLite история чатов
  - `tools.py` — описания tools для Claude
  - `composite_agent.py` — агентный цикл с tool-use
  - `api_server.py` — FastAPI сервер (опционально)
  - `local_test.py` — локальная проверка без API

## Деплой на Ubuntu (systemd)
1. Скопируйте репозиторий на сервер, выполните шаги из «Быстрый старт».
2. Создайте сервис `/etc/systemd/system/clickhouse-agent.service`:
   ```
   [Unit]
   Description=ClickHouse Analysis Agent
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/root/agent
   ExecStart=/root/agent/venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
   Restart=always
   RestartSec=5
   EnvironmentFile=/root/agent/.env

   [Install]
   WantedBy=multi-user.target
   ```
3. Активируйте сервис:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now clickhouse-agent.service
   sudo systemctl status clickhouse-agent.service
   ```
4. (Опционально) Настройте Nginx reverse-proxy на `http://127.0.0.1:8000` и включите длинный `proxy_read_timeout` (300s), чтобы не прерывать долгие запросы.

## Примечания
- Агент использует Parquet вместо CSV, чтобы сохранить сложные типы ClickHouse.
- Python-код исполняется с доступом к `df`, `pd`, `np`, `plt`, `sns`; все matplotlib фигуры автоматически кодируются в base64.
- История чатов хранится в SQLite с окном последних 20 сообщений на сессию и TTL 24 часа.
