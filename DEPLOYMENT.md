# Руководство по развертыванию на сервере Beget (server.asktab.ru)

## Содержание
1. [Требования](#требования)
2. [Подготовка сервера](#подготовка-сервера)
3. [Установка проекта](#установка-проекта)
4. [Настройка базы данных ClickHouse](#настройка-базы-данных-clickhouse)
5. [Настройка API сервера](#настройка-api-сервера)
   - 5.1. [Редактирование файла конфигурации](#1-редактирование-файла-конфигурации)
   - 5.2. [Заполнить переменные окружения](#2-заполнить-переменные-окружения)
   - 5.3. [Настройка базы данных SQLite](#3-настройка-базы-данных-sqlite)
   - 5.4. [Настройка Python Sandbox (exec() функция)](#4-настройка-python-sandbox-exec-функция)
   - 5.5. [Проверка конфигурации](#5-проверка-конфигурации)
6. [Настройка автозапуска (systemd)](#настройка-автозапуска-systemd)
7. [Настройка веб-сервера (nginx)](#настройка-веб-сервера-nginx)
8. [Запуск и тестирование](#запуск-и-тестирование)
9. [Мониторинг и логи](#мониторинг-и-логи)
10. [Устранение неполадок](#устранение-неполадок)

---

## Требования

### Сервер
- **Хостинг**: Beget (или VPS с Ubuntu 20.04+)
- **Домен**: server.asktab.ru (настроен на Beget)
- **Python**: 3.11 или выше
- **RAM**: минимум 2GB
- **Доступ**: SSH доступ к серверу

### Внешние сервисы
- **Anthropic API**: API ключ для Claude Sonnet 4 ([получить здесь](https://console.anthropic.com/))
- **ClickHouse**: база данных (Яндекс Cloud или другой хостинг)

---

## Подготовка сервера

### 1. Подключение к серверу через SSH

```bash
# Подключение к Beget серверу
ssh username@server.asktab.ru
# или используйте IP адрес
ssh username@123.456.789.012
```

### 2. Обновление системы

```bash
# Обновление списка пакетов
sudo apt update

# Обновление установленных пакетов
sudo apt upgrade -y

# Установка необходимых инструментов
sudo apt install -y python3 python3-pip python3-venv git wget curl nginx
```

### 3. Проверка версии Python

```bash
python3 --version
# Должна быть версия 3.11 или выше
```

Если версия ниже 3.11, установите новую версию:

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

---

## Установка проекта

### 1. Выбор директории для установки

```bash
# Переход в домашнюю директорию
cd ~

# Или создание специальной директории для приложений
sudo mkdir -p /opt/agent_api
cd /opt/agent_api
```

### 2. Клонирование репозитория

```bash
# Клонирование проекта
git clone https://github.com/vdubrovin1704-ops/agent_clickhouse_python_v1.git
cd agent_clickhouse_python_v1
```

### 3. Запуск скрипта установки

```bash
# Сделать скрипт исполняемым (если не исполняемый)
chmod +x setup.sh

# Запустить установку
./setup.sh
```

Этот скрипт:
- Создаст виртуальное окружение `venv`
- Установит все Python зависимости
- Скачает SSL сертификат для ClickHouse (Яндекс Cloud)
- Создаст файл `.env` из шаблона

---

## Настройка базы данных ClickHouse

### Вариант 1: Использование существующей базы данных

Если у вас уже есть ClickHouse база данных (например, в Яндекс Cloud):

1. **Получите данные для подключения:**
   - Хост: `your-cluster.mdb.yandexcloud.net`
   - Порт: `8443` (для HTTPS)
   - Пользователь: `your_username`
   - Пароль: `your_password`
   - База данных: `your_database`

2. **Проверьте доступность базы:**
   ```bash
   curl -v "https://your-cluster.mdb.yandexcloud.net:8443" \
     --cacert YandexInternalRootCA.crt
   ```

### Вариант 2: Создание новой базы данных в Яндекс Cloud

```bash
# Установка Яндекс Cloud CLI (если нужно)
curl -sSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash

# Инициализация
yc init

# Создание кластера ClickHouse (пример)
yc managed-clickhouse cluster create \
  --name my-clickhouse \
  --environment production \
  --network-name default \
  --clickhouse-resource-preset s2.micro \
  --clickhouse-disk-type network-ssd \
  --clickhouse-disk-size 10 \
  --user name=admin,password=YourSecurePassword123 \
  --database name=analytics
```

### Вариант 3: Использование локальной ClickHouse

```bash
# Установка ClickHouse на сервер
curl https://clickhouse.com/ | sh
sudo ./clickhouse install

# Запуск ClickHouse
sudo clickhouse start

# Создание базы данных
clickhouse-client --query "CREATE DATABASE IF NOT EXISTS analytics"
```

### Создание тестовых таблиц (опционально)

```sql
-- Подключение к ClickHouse
clickhouse-client --host your-host --port 9440 --secure --user admin --password YourPassword

-- Создание тестовой таблицы
CREATE TABLE IF NOT EXISTS analytics.sales (
    date Date,
    product_name String,
    category String,
    revenue Decimal(10, 2),
    quantity UInt32
) ENGINE = MergeTree()
ORDER BY date;

-- Вставка тестовых данных
INSERT INTO analytics.sales VALUES
    ('2024-01-01', 'Laptop', 'Electronics', 1200.00, 5),
    ('2024-01-02', 'Phone', 'Electronics', 800.00, 10),
    ('2024-01-03', 'Headphones', 'Accessories', 150.00, 20);
```

---

## Настройка API сервера

### 1. Редактирование файла конфигурации

```bash
# Открыть .env файл для редактирования
nano .env
```

### 2. Заполнить переменные окружения

```bash
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-api03-ваш-ключ-здесь

# ClickHouse
CLICKHOUSE_HOST=your-cluster.mdb.yandexcloud.net
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=admin
CLICKHOUSE_PASSWORD=YourSecurePassword123
CLICKHOUSE_DATABASE=analytics
CLICKHOUSE_SSL_CERT_PATH=YandexInternalRootCA.crt

# Сервер
SERVER_URL=https://server.asktab.ru
```

**Сохранение**: `Ctrl+O`, затем `Enter`, затем `Ctrl+X`

### 3. Настройка базы данных SQLite

Проект использует **SQLite** для хранения истории переписок и сессий пользователей. База данных создаётся автоматически при первом запуске.

#### Основные параметры

- **Файл базы данных**: `./chat_history.db` (создаётся в корневой директории проекта)
- **Максимум сообщений на сессию**: 20 (скользящее окно)
- **Срок жизни сессии (TTL)**: 24 часа

#### Структура базы данных

SQLite база данных содержит две таблицы:

```sql
-- Таблица сессий
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT (datetime('now')),
    last_activity TEXT DEFAULT (datetime('now'))
);

-- Таблица сообщений
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Индекс для быстрого поиска
CREATE INDEX idx_msg_session ON messages(session_id, created_at);
```

#### Особенности работы

1. **WAL режим**: База данных работает в режиме Write-Ahead Logging для лучшей производительности при параллельных запросах
2. **Скользящее окно**: Для каждой сессии сохраняются только последние 20 сообщений
3. **Автоматическая очистка**: Сессии старше 24 часов автоматически удаляются
4. **UTF-8 поддержка**: Полная поддержка русского языка и emoji

#### Просмотр статистики базы данных

```bash
# Проверка размера базы данных
du -h chat_history.db

# Подключение к SQLite для просмотра данных
sqlite3 chat_history.db

# Примеры SQL запросов в sqlite3:
sqlite> SELECT COUNT(*) FROM sessions;
sqlite> SELECT COUNT(*) FROM messages;
sqlite> SELECT session_id, COUNT(*) as msg_count FROM messages GROUP BY session_id;
sqlite> .quit
```

#### Ручное управление базой данных

```bash
# Создание резервной копии
cp chat_history.db chat_history_backup_$(date +%Y%m%d).db

# Очистка базы данных (удаление всех данных)
rm chat_history.db
# База будет автоматически пересоздана при следующем запуске

# Проверка целостности базы данных
sqlite3 chat_history.db "PRAGMA integrity_check;"
```

#### Мониторинг через API

Агент предоставляет эндпоинт для получения статистики:

```bash
curl http://localhost:8000/api/chat-stats

# Ответ:
# {
#   "active_sessions": 15,
#   "total_messages": 342,
#   "db_size_mb": 0.52
# }
```

### 4. Настройка Python Sandbox (exec() функция)

Проект использует **безопасное выполнение Python кода** через функцию `exec()` для анализа данных из файлов Parquet.

#### Принцип работы

1. ClickHouse выполняет SQL запрос и экспортирует результаты в **Parquet файл**
2. Python Sandbox загружает данные из Parquet в DataFrame
3. AI агент генерирует Python код для анализа
4. Код выполняется в изолированном окружении с помощью `exec()`
5. Результаты (текст, графики) возвращаются пользователю

#### Доступные библиотеки

В песочнице доступны следующие библиотеки:

- **pandas** (как `pd`) - для работы с DataFrame
- **numpy** (как `np`) - для численных вычислений
- **matplotlib.pyplot** (как `plt`) - для создания графиков
- **seaborn** (как `sns`) - для статистических визуализаций

#### Переменные в exec() окружении

```python
local_vars = {
    "df": df,           # pandas DataFrame с данными из Parquet
    "pd": pd,           # модуль pandas
    "np": np,           # модуль numpy
    "plt": plt,         # matplotlib.pyplot
    "sns": sns,         # seaborn
    "result": None,     # переменная для возврата результата
}
```

#### Безопасность

1. **Ограниченное пространство имён**: Код выполняется с ограниченным доступом к глобальным переменным
2. **Изоляция**: Нет доступа к файловой системе, сети или системным вызовам
3. **Захват ошибок**: Все исключения перехватываются и возвращаются в читаемом виде
4. **Очистка памяти**: После выполнения все фигуры matplotlib и переменные очищаются

#### Пример использования

```python
# Пример Python кода, который выполняется в песочнице:
import matplotlib.pyplot as plt

# Анализ данных
top_products = df.groupby('product_name')['revenue'].sum().sort_values(ascending=False).head(5)

# Создание графика
plt.figure(figsize=(10, 6))
top_products.plot(kind='bar')
plt.title('Топ 5 продуктов по выручке')
plt.ylabel('Выручка')
plt.xlabel('Продукт')
plt.xticks(rotation=45)
plt.tight_layout()

# Сохранение результата
result = f"Найдено {len(df)} записей. Топ продукт: {top_products.index[0]}"
```

#### Matplotlib конфигурация

Проект использует backend **'Agg'** для серверного рендеринга графиков:

```python
matplotlib.use('Agg')  # Обязательно для работы на сервере без дисплея
```

Настройки по умолчанию:
- Размер фигуры: 10x6 дюймов
- DPI: 150 (для качественных изображений)
- Стиль: seaborn whitegrid
- Шрифт: 12pt

#### Parquet файлы

Временные Parquet файлы сохраняются в директории `./temp_data/`:

```bash
# Просмотр временных файлов
ls -lh temp_data/

# Автоматическая очистка файлов старше 1 часа
find temp_data/ -name "query_*.parquet" -mtime +0.04167 -delete

# Ручная очистка всех временных файлов
rm -f temp_data/query_*.parquet
```

#### Проверка работы Python Sandbox

```bash
# Активация виртуального окружения
source venv/bin/activate

# Запуск тестового агента
python test_agent.py

# Примеры запросов для проверки:
# "Покажи список всех таблиц"
# "Выполни запрос SELECT * FROM sales LIMIT 10"
# "Построй график продаж по датам"
```

### 5. Проверка конфигурации

```bash
# Активация виртуального окружения
source venv/bin/activate

# Тестовый запуск агента
python test_agent.py
```

Попробуйте запрос: `Покажи список всех таблиц в базе данных`

Если всё работает, переходите к следующему шагу.

---

## Настройка автозапуска (systemd)

### 1. Создание systemd сервиса

```bash
# Создание файла сервиса
sudo nano /etc/systemd/system/agent-api.service
```

### 2. Содержимое файла сервиса

```ini
[Unit]
Description=ClickHouse Analysis Agent API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/agent_api/agent_clickhouse_python_v1
Environment="PATH=/opt/agent_api/agent_clickhouse_python_v1/venv/bin"
ExecStart=/opt/agent_api/agent_clickhouse_python_v1/venv/bin/python api_server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Загрузка переменных окружения из .env
EnvironmentFile=/opt/agent_api/agent_clickhouse_python_v1/.env

[Install]
WantedBy=multi-user.target
```

**Важно**: Замените пути на актуальные для вашего сервера!

### 3. Активация и запуск сервиса

```bash
# Перезагрузка конфигурации systemd
sudo systemctl daemon-reload

# Включение автозапуска при загрузке системы
sudo systemctl enable agent-api.service

# Запуск сервиса
sudo systemctl start agent-api.service

# Проверка статуса
sudo systemctl status agent-api.service
```

### 4. Проверка работы API

```bash
# Проверка что API отвечает
curl http://localhost:8000/

# Должен вернуться JSON:
# {"status":"online","model":"Claude Sonnet 4","service":"ClickHouse Analysis Agent"}
```

---

## Настройка веб-сервера (nginx)

### 1. Создание конфигурации nginx

```bash
# Создание файла конфигурации
sudo nano /etc/nginx/sites-available/agent-api
```

### 2. Содержимое конфигурации

```nginx
server {
    listen 80;
    server_name server.asktab.ru;

    # Перенаправление на HTTPS (после настройки SSL)
    # return 301 https://$server_name$request_uri;

    # Проксирование API запросов
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Увеличение таймаутов для долгих запросов
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    # Статический веб-интерфейс
    location / {
        root /opt/agent_api/agent_clickhouse_python_v1/static;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Логи
    access_log /var/log/nginx/agent-api-access.log;
    error_log /var/log/nginx/agent-api-error.log;
}
```

### 3. Активация конфигурации

```bash
# Создание символической ссылки
sudo ln -s /etc/nginx/sites-available/agent-api /etc/nginx/sites-enabled/

# Проверка конфигурации nginx
sudo nginx -t

# Перезапуск nginx
sudo systemctl restart nginx
```

### 4. Настройка SSL (HTTPS) с Let's Encrypt

```bash
# Установка Certbot
sudo apt install -y certbot python3-certbot-nginx

# Получение SSL сертификата
sudo certbot --nginx -d server.asktab.ru

# Автоматическое обновление сертификата
sudo certbot renew --dry-run
```

После настройки SSL, раскомментируйте строку `return 301 https://...` в конфигурации nginx.

---

## Запуск и тестирование

### 1. Проверка всех сервисов

```bash
# Проверка статуса API сервера
sudo systemctl status agent-api.service

# Проверка статуса nginx
sudo systemctl status nginx

# Проверка портов
sudo netstat -tlnp | grep -E '(8000|80|443)'
```

### 2. Тестирование через curl

```bash
# Проверка health endpoint
curl http://server.asktab.ru/health

# Проверка info endpoint
curl http://server.asktab.ru/api/info

# Тестовый запрос к API
curl -X POST http://server.asktab.ru/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Покажи список всех таблиц в базе данных"
  }'
```

### 3. Тестирование через веб-интерфейс

Откройте браузер и перейдите на:
```
http://server.asktab.ru
```

Вы должны увидеть веб-интерфейс для тестирования API.

---

## Мониторинг и логи

### Просмотр логов API сервера

```bash
# Логи в реальном времени
sudo journalctl -u agent-api.service -f

# Последние 100 строк логов
sudo journalctl -u agent-api.service -n 100

# Логи за последний час
sudo journalctl -u agent-api.service --since "1 hour ago"
```

### Просмотр логов nginx

```bash
# Access логи
sudo tail -f /var/log/nginx/agent-api-access.log

# Error логи
sudo tail -f /var/log/nginx/agent-api-error.log
```

### Мониторинг ресурсов

```bash
# Использование CPU и памяти
htop

# Проверка дискового пространства
df -h

# Проверка использования памяти
free -h
```

### Автоматическая очистка логов

```bash
# Настройка journald для ограничения размера логов
sudo nano /etc/systemd/journald.conf

# Добавить/изменить:
# SystemMaxUse=500M
# MaxRetentionSec=7day

# Перезапустить journald
sudo systemctl restart systemd-journald
```

---

## Устранение неполадок

### Проблема: API сервер не запускается

```bash
# Проверка логов
sudo journalctl -u agent-api.service -n 50

# Проверка .env файла
cat .env | grep -v PASSWORD

# Ручной запуск для диагностики
cd /opt/agent_api/agent_clickhouse_python_v1
source venv/bin/activate
python api_server.py
```

### Проблема: Ошибка подключения к ClickHouse

```bash
# Проверка сертификата
ls -lh YandexInternalRootCA.crt

# Проверка доступности ClickHouse
curl -v "https://your-host.mdb.yandexcloud.net:8443" \
  --cacert YandexInternalRootCA.crt

# Проверка переменных окружения
source .env
echo $CLICKHOUSE_HOST
echo $CLICKHOUSE_USER
```

### Проблема: nginx возвращает 502 Bad Gateway

```bash
# Проверка что API сервер работает
curl http://localhost:8000/

# Проверка логов nginx
sudo tail -f /var/log/nginx/agent-api-error.log

# Перезапуск API сервера
sudo systemctl restart agent-api.service
```

### Проблема: Недостаточно прав доступа

```bash
# Изменение владельца директории
sudo chown -R $USER:$USER /opt/agent_api/agent_clickhouse_python_v1

# Изменение прав на .env файл
chmod 600 .env
```

### Проблема: Ошибка Anthropic API

```bash
# Проверка API ключа
source .env
echo $ANTHROPIC_API_KEY | cut -c1-10

# Тестирование API напрямую
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## Обновление проекта

### Обновление кода

```bash
# Переход в директорию проекта
cd /opt/agent_api/agent_clickhouse_python_v1

# Получение обновлений
git pull origin main

# Обновление зависимостей (если изменились)
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Перезапуск сервиса
sudo systemctl restart agent-api.service
```

### Обновление зависимостей

```bash
# Активация виртуального окружения
source venv/bin/activate

# Обновление всех зависимостей
pip install -r requirements.txt --upgrade

# Перезапуск сервиса
sudo systemctl restart agent-api.service
```

---

## Резервное копирование

### Автоматическое резервное копирование базы данных SQLite

```bash
# Создание скрипта резервного копирования
sudo nano /opt/agent_api/backup.sh
```

Содержимое:
```bash
#!/bin/bash
BACKUP_DIR="/opt/agent_api/backups"
PROJECT_DIR="/opt/agent_api/agent_clickhouse_python_v1"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Резервное копирование SQLite базы
if [ -f "$PROJECT_DIR/chat_history.db" ]; then
    cp "$PROJECT_DIR/chat_history.db" "$BACKUP_DIR/chat_history_$DATE.db"
    echo "✓ Backup created: chat_history_$DATE.db"
fi

# Удаление старых бэкапов (старше 7 дней)
find $BACKUP_DIR -name "chat_history_*.db" -mtime +7 -delete

echo "✓ Backup completed"
```

Настройка автоматического запуска:
```bash
# Сделать скрипт исполняемым
sudo chmod +x /opt/agent_api/backup.sh

# Добавить в crontab (запуск каждый день в 3:00)
sudo crontab -e

# Добавить строку:
0 3 * * * /opt/agent_api/backup.sh >> /var/log/agent-backup.log 2>&1
```

---

## Масштабирование (опционально)

### Использование Gunicorn для production

Установка:
```bash
source venv/bin/activate
pip install gunicorn
```

Изменение ExecStart в systemd сервисе:
```ini
ExecStart=/opt/agent_api/agent_clickhouse_python_v1/venv/bin/gunicorn \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    -b 127.0.0.1:8000 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile - \
    api_server:app
```

Перезапуск:
```bash
sudo systemctl daemon-reload
sudo systemctl restart agent-api.service
```

---

## Безопасность

### Рекомендации по безопасности

1. **Защита .env файла:**
   ```bash
   chmod 600 .env
   ```

2. **Настройка firewall:**
   ```bash
   sudo ufw allow 22    # SSH
   sudo ufw allow 80    # HTTP
   sudo ufw allow 443   # HTTPS
   sudo ufw enable
   ```

3. **Ограничение доступа к API (если нужно):**

   Добавить в nginx конфигурацию:
   ```nginx
   # Ограничение по IP
   location /api/ {
       allow 123.456.789.0/24;  # ваша подсеть
       deny all;

       proxy_pass http://127.0.0.1:8000/api/;
       # ... остальная конфигурация
   }
   ```

4. **Rate limiting в nginx:**
   ```nginx
   # В блоке http
   limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

   # В блоке location /api/
   limit_req zone=api_limit burst=20 nodelay;
   ```

---

## Контакты и поддержка

Если возникли проблемы:
1. Проверьте логи: `sudo journalctl -u agent-api.service -f`
2. Проверьте nginx логи: `sudo tail -f /var/log/nginx/agent-api-error.log`
3. Создайте Issue в GitHub репозитории

---

**Готово!** Ваш API сервер теперь работает на `https://server.asktab.ru` и доступен для использования с фронтенд приложением.
