# Быстрое руководство по развертыванию на server.asktab.ru

## 🚀 Краткая инструкция (5 минут)

Это упрощенное руководство для быстрого запуска. Полная инструкция находится в [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Шаг 1: Подключение к серверу

```bash
ssh username@server.asktab.ru
```

---

## Шаг 2: Установка проекта

```bash
# Переход в директорию (или создание новой)
cd /opt
sudo mkdir -p agent_api
cd agent_api

# Клонирование проекта
git clone https://github.com/vdubrovin1704-ops/agent_clickhouse_python_v1.git
cd agent_clickhouse_python_v1

# Запуск автоматической установки
./setup.sh
```

---

## Шаг 3: Настройка конфигурации

```bash
# Редактирование .env файла
nano .env
```

Заполните следующие параметры:

```bash
# Anthropic API (получить на https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-api03-ваш-ключ

# ClickHouse (ваша база данных)
CLICKHOUSE_HOST=your-cluster.mdb.yandexcloud.net
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=admin
CLICKHOUSE_PASSWORD=ваш-пароль
CLICKHOUSE_DATABASE=analytics
CLICKHOUSE_SSL_CERT_PATH=YandexInternalRootCA.crt

# URL сервера
SERVER_URL=https://server.asktab.ru
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## Шаг 4: Тестирование

```bash
# Активация виртуального окружения
source venv/bin/activate

# Тестовый запуск
python test_agent.py

# Введите: "Покажи список всех таблиц в базе данных"
# Если работает - переходите к следующему шагу
```

---

## Шаг 5: Настройка systemd службы

```bash
# Копирование файла службы
sudo cp agent-api.service /etc/systemd/system/

# ВАЖНО: Отредактируйте пути в файле службы
sudo nano /etc/systemd/system/agent-api.service
# Замените /opt/agent_api/agent_clickhouse_python_v1 на ваш актуальный путь

# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable agent-api.service

# Запуск службы
sudo systemctl start agent-api.service

# Проверка статуса
sudo systemctl status agent-api.service

# Проверка работы API
curl http://localhost:8000/
```

---

## Шаг 6: Настройка nginx

```bash
# Копирование конфигурации nginx
sudo cp nginx.conf /etc/nginx/sites-available/agent-api

# ВАЖНО: Отредактируйте пути в конфигурации
sudo nano /etc/nginx/sites-available/agent-api
# Замените /opt/agent_api/agent_clickhouse_python_v1 на ваш актуальный путь

# Активация конфигурации
sudo ln -s /etc/nginx/sites-available/agent-api /etc/nginx/sites-enabled/

# Проверка конфигурации
sudo nginx -t

# Перезапуск nginx
sudo systemctl restart nginx
```

---

## Шаг 7: Настройка SSL (HTTPS)

```bash
# Установка Certbot
sudo apt install -y certbot python3-certbot-nginx

# Получение SSL сертификата
sudo certbot --nginx -d server.asktab.ru

# Следуйте инструкциям на экране
# Certbot автоматически настроит HTTPS
```

---

## Шаг 8: Проверка работы

### Через curl:

```bash
# Health check
curl https://server.asktab.ru/health

# API info
curl https://server.asktab.ru/api/info

# Тестовый запрос
curl -X POST https://server.asktab.ru/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "Покажи список всех таблиц в базе данных"}'
```

### Через браузер:

Откройте в браузере:
```
https://server.asktab.ru
```

Вы должны увидеть веб-интерфейс для тестирования API.

---

## 🎉 Готово!

Ваш API сервер запущен и доступен по адресу `https://server.asktab.ru`

---

## 📊 Полезные команды

### Просмотр логов API:
```bash
sudo journalctl -u agent-api.service -f
```

### Просмотр логов nginx:
```bash
sudo tail -f /var/log/nginx/agent-api-error.log
```

### Перезапуск службы:
```bash
sudo systemctl restart agent-api.service
```

### Остановка службы:
```bash
sudo systemctl stop agent-api.service
```

### Проверка статуса:
```bash
sudo systemctl status agent-api.service
```

---

## 🐛 Устранение проблем

### API не запускается

```bash
# Проверка логов
sudo journalctl -u agent-api.service -n 50

# Ручной запуск для диагностики
cd /opt/agent_api/agent_clickhouse_python_v1
source venv/bin/activate
python api_server.py
```

### nginx возвращает 502 Bad Gateway

```bash
# Проверка что API работает
curl http://localhost:8000/

# Перезапуск API
sudo systemctl restart agent-api.service

# Проверка логов nginx
sudo tail -f /var/log/nginx/agent-api-error.log
```

### Ошибка подключения к ClickHouse

```bash
# Проверка конфигурации
cat .env | grep CLICKHOUSE

# Проверка сертификата
ls -lh YandexInternalRootCA.crt

# Тестирование подключения
source venv/bin/activate
python -c "from clickhouse_client import ClickHouseClient; client = ClickHouseClient(); print(client.list_tables())"
```

---

## 📚 Дополнительная информация

- **Полная инструкция**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Документация API**: [README.md](README.md)
- **Установка и настройка**: [INSTALLATION.md](INSTALLATION.md)

---

## 🔒 Важные замечания

1. **Безопасность .env файла:**
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

3. **Регулярное обновление:**
   ```bash
   cd /opt/agent_api/agent_clickhouse_python_v1
   git pull origin main
   sudo systemctl restart agent-api.service
   ```

---

## 💬 Поддержка

Если возникли проблемы, создайте Issue в GitHub репозитории.

---

**Успешного развертывания!** 🚀
