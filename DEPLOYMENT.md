# Инструкция по запуску агента на Ubuntu сервере

## Требования

- Ubuntu 20.04 / 22.04 / 24.04
- Python 3.11+
- Доступ в интернет (для Anthropic API и ClickHouse)
- Учётная запись Anthropic с API ключом
- Данные подключения к ClickHouse (Яндекс Cloud)

---

## 1. Подготовка сервера

### 1.1 Установить системные зависимости

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git wget curl
```

Проверить версию Python:
```bash
python3 --version   # Должно быть 3.11+
```

### 1.2 Скопировать файлы проекта

```bash
# Вариант A: клонировать репозиторий
git clone https://github.com/vdubrovin1704-ops/agent_clickhouse_python_v1.git
cd agent_clickhouse_python_v1/composite_agent

# Вариант B: вручную скопировать папку composite_agent/ на сервер
# scp -r composite_agent/ user@server:/root/composite_agent
cd /root/composite_agent
```

---

## 2. Установка зависимостей

Из директории `composite_agent/` запустить скрипт установки:

```bash
chmod +x setup.sh
./setup.sh
```

Скрипт:
1. Создаст virtualenv в `venv/`
2. Установит все Python-пакеты из `requirements.txt`
3. Скачает SSL сертификат для Яндекс Cloud ClickHouse (`YandexInternalRootCA.crt`)
4. Создаст файл `.env` из шаблона `.env.example`

---

## 3. Настройка конфигурации

Отредактировать файл `.env`:

```bash
nano .env
```

Заполнить значения:

```dotenv
# Anthropic API ключ (получить на https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-api03-...

# ClickHouse (Яндекс Cloud)
CLICKHOUSE_HOST=rc1a-xxxxxxxxxx.mdb.yandexcloud.net
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=user
CLICKHOUSE_PASSWORD=your_password
CLICKHOUSE_DATABASE=your_database

# SSL сертификат (уже скачан скриптом setup.sh)
CLICKHOUSE_SSL_CERT_PATH=YandexInternalRootCA.crt

# URL сервера (опционально, для веб-интерфейса)
SERVER_URL=https://your-server.example.com
```

> **Важно**: файл `.env` содержит секреты — не коммитить в git.

---

## 4. Тестирование агента

### 4.1 Активировать virtualenv

```bash
source venv/bin/activate
```

### 4.2 Запустить интерактивный тест

```bash
python test_agent.py
```

Агент откроет интерактивный диалог в терминале. Пример первого запроса:

```
❓ Ваш запрос: Покажи структуру таблиц в базе данных
```

Агент вызовет `list_tables`, отобразит схему и ответит на русском языке.

### 4.3 Одиночный запрос

```bash
python test_agent.py "Покажи топ-10 записей из таблицы orders"
```

### 4.4 Продолжение сессии

```bash
# Запустить с конкретным session_id для продолжения диалога
python test_agent.py --session my-session-123 "Теперь построй график"
```

### 4.5 Сохранение графиков

Все графики автоматически сохраняются в `output_plots/` в виде PNG файлов.

---

## 5. Запуск API сервера (опционально)

API сервер нужен для будущей интеграции с веб-интерфейсом.

### 5.1 Запустить вручную

```bash
source venv/bin/activate
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

Проверить что работает:
```bash
curl http://localhost:8000/health
# {"status":"healthy","timestamp":"2026-02-23T12:00:00"}
```

Отправить запрос:
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "Покажи структуру таблиц"}'
```

### 5.2 Настроить systemd (автозапуск)

Скопировать файл сервиса:
```bash
sudo cp agent.service /etc/systemd/system/agent.service
```

Отредактировать пути если нужно (по умолчанию `/root/composite_agent`):
```bash
sudo nano /etc/systemd/system/agent.service
```

Включить и запустить:
```bash
sudo systemctl daemon-reload
sudo systemctl enable agent
sudo systemctl start agent
sudo systemctl status agent
```

Логи:
```bash
sudo journalctl -u agent -f
```

### 5.3 Настроить Nginx (reverse proxy)

Установить Nginx:
```bash
sudo apt install -y nginx
```

Скопировать конфигурацию:
```bash
sudo cp nginx_agent.conf /etc/nginx/sites-available/agent
sudo ln -s /etc/nginx/sites-available/agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Отредактировать `server_name` в конфиге под ваш домен:
```bash
sudo nano /etc/nginx/sites-available/agent
```

Получить SSL сертификат (Let's Encrypt):
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-server.example.com
```

---

## 6. Структура проекта

```
composite_agent/
├── .env                    ← конфигурация (создаётся из .env.example)
├── .env.example            ← шаблон конфигурации
├── .gitignore
├── requirements.txt        ← Python зависимости
├── setup.sh                ← скрипт установки
│
├── config.py               ← загрузка конфигурации из .env
├── clickhouse_client.py    ← подключение к ClickHouse, выгрузка в Parquet
├── python_sandbox.py       ← exec Python-кода с захватом графиков
├── chat_storage.py         ← SQLite история диалога
├── tools.py                ← описание инструментов для Claude
├── composite_agent.py      ← главный агент (цикл tool_use)
├── api_server.py           ← FastAPI сервер
│
├── test_agent.py           ← тестовый CLI скрипт
├── agent.service           ← systemd сервис
├── nginx_agent.conf        ← nginx конфигурация
│
├── temp_data/              ← временные parquet файлы (автоочистка)
├── output_plots/           ← графики из тестов
└── chat_history.db         ← SQLite база (создаётся автоматически)
```

---

## 7. Устранение проблем

### Ошибка подключения к ClickHouse

```
connection refused / SSL error
```

- Проверьте `CLICKHOUSE_HOST` — должен быть без `https://`
- Убедитесь что `YandexInternalRootCA.crt` существует (или уберите `CLICKHOUSE_SSL_CERT_PATH`)
- Проверьте `CLICKHOUSE_PORT=8443` (для Яндекс Cloud)

### Ошибка Anthropic API

```
AuthenticationError: invalid api_key
```

- Проверьте `ANTHROPIC_API_KEY` в `.env`
- Убедитесь что у вас есть доступ к модели `claude-sonnet-4-5`

### Ошибка импорта модуля

```
ModuleNotFoundError: No module named 'anthropic'
```

- Активируйте virtualenv: `source venv/bin/activate`
- Переустановите зависимости: `pip install -r requirements.txt`

### Matplotlib не отображает графики

Графики не отображаются в терминале — это нормально.
Они сохраняются в `output_plots/` как PNG файлы.
При использовании API сервера — возвращаются в JSON как base64.

---

## 8. Безопасность

- Файл `.env` добавлен в `.gitignore` — не коммитить в репозиторий
- Директория `temp_data/` очищается автоматически каждый час
- История чатов хранится локально в SQLite (`chat_history.db`)
- В Python sandbox разрешены только встроенные функции Python (`__builtins__`)
- Выполняются только SELECT запросы к ClickHouse
