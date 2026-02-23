# Инструкция по запуску агента на Ubuntu

## Требования

- **Ubuntu 20.04+** (рекомендуется 22.04 LTS)
- **Python 3.11+**
- Доступ к ClickHouse (Яндекс Cloud или другой)
- API-ключ Anthropic (`ANTHROPIC_API_KEY`)

---

## 1. Установка системных пакетов

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip wget git
```

Если Python 3.11 недоступен:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv
```

---

## 2. Клонирование и установка

```bash
cd ~
git clone <URL_РЕПОЗИТОРИЯ> agent
cd agent

# Запустить установочный скрипт
chmod +x setup.sh
./setup.sh
```

Скрипт `setup.sh`:
- Создаст виртуальное окружение `venv/`
- Установит зависимости из `requirements.txt`
- Скачает SSL-сертификат для Яндекс Cloud ClickHouse
- Создаст `.env` из шаблона `.env.example`

---

## 3. Настройка .env

Отредактируйте файл `.env`:

```bash
nano .env
```

Заполните:

```
ANTHROPIC_API_KEY=sk-ant-ваш-ключ
CLICKHOUSE_HOST=ваш-хост.mdb.yandexcloud.net
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=ваш_пользователь
CLICKHOUSE_PASSWORD=ваш_пароль
CLICKHOUSE_DATABASE=ваша_база
CLICKHOUSE_SSL_CERT_PATH=YandexInternalRootCA.crt
```

---

## 4. Тестирование в CLI

```bash
source venv/bin/activate
python test_agent.py
```

Введите запрос, например:
```
Покажи все таблицы в базе
```

Агент:
1. Подключится к ClickHouse
2. Выгрузит данные
3. Проанализирует с помощью Python
4. Выведет текст, таблицы и сохранит графики в PNG

---

## 5. Запуск API-сервера (опционально)

```bash
source venv/bin/activate
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Проверка:
```bash
curl http://localhost:8000/health
```

Отправка запроса:
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "Покажи все таблицы в базе"}'
```

---

## 6. Systemd-сервис (для production)

Создайте файл `/etc/systemd/system/ch-agent.service`:

```ini
[Unit]
Description=ClickHouse Analysis Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/agent
ExecStart=/root/agent/venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/root/agent/.env

[Install]
WantedBy=multi-user.target
```

Активация:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ch-agent
sudo systemctl start ch-agent
sudo systemctl status ch-agent
```

Логи:
```bash
sudo journalctl -u ch-agent -f
```

---

## 7. Nginx (HTTPS проксирование)

Установите Nginx и настройте SSL (certbot):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Файл `/etc/nginx/sites-available/ch-agent`:

```nginx
server {
    listen 443 ssl;
    server_name server.asktab.ru;

    ssl_certificate /etc/letsencrypt/live/server.asktab.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/server.asktab.ru/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ch-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Структура проекта

```
agent/
├── .env                    # Конфигурация (не в git)
├── .env.example            # Шаблон конфигурации
├── requirements.txt        # Зависимости Python
├── config.py               # Загрузка конфигурации из .env
├── clickhouse_client.py    # Клиент ClickHouse (подключение, SQL, Parquet)
├── python_sandbox.py       # Выполнение Python-кода (exec + matplotlib)
├── chat_storage.py         # SQLite хранилище истории чатов
├── tools.py                # Определения tools для Claude
├── composite_agent.py      # Главный агент — цикл tool_use
├── api_server.py           # FastAPI сервер (HTTP endpoints)
├── test_agent.py           # Тестовый CLI-скрипт
├── setup.sh                # Скрипт установки
└── DEPLOY.md               # Эта инструкция
```
