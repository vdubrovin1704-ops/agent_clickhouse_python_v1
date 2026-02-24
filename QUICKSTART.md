# Быстрый старт

## Минимальная установка (5 минут)

### 1. Клонирование и установка

```bash
# Клонировать репозиторий
git clone https://github.com/vdubrovin1704-ops/agent_clickhouse_python_v1.git
cd agent_clickhouse_python_v1

# Запустить скрипт установки
bash setup.sh
```

### 2. Настройка

```bash
# Отредактировать .env
nano .env
```

**Минимально необходимые настройки:**

```bash
ANTHROPIC_API_KEY=sk-ant-api03-ваш-ключ
CLICKHOUSE_HOST=ваш-хост.mdb.yandexcloud.net
CLICKHOUSE_USER=ваш_пользователь
CLICKHOUSE_PASSWORD=ваш_пароль
CLICKHOUSE_DATABASE=ваша_база
```

### 3. Запуск

```bash
# Активировать окружение
source venv/bin/activate

# Запустить тестовый агент
python test_agent.py
```

### 4. Первый запрос

```
❓ Ваш запрос: Покажи список таблиц в базе данных
```

## Типичные сценарии использования

### Сценарий 1: Просмотр данных

```
❓ Покажи первые 10 записей из таблицы orders
```

### Сценарий 2: Агрегация с визуализацией

```
❓ Посчитай выручку по месяцам за 2024 год и построй line chart
```

### Сценарий 3: Топ-N анализ

```
❓ Покажи топ-10 клиентов по количеству заказов с bar chart
```

### Сценарий 4: Сложная аналитика

```
❓ Проанализируй продажи: покажи тренд, сезонность и выбросы. Построй графики.
```

## Что делать если...

### Ошибка подключения к ClickHouse

```
❌ Could not connect to ClickHouse
```

**Решение:**
1. Проверьте данные в `.env`
2. Проверьте наличие `YandexInternalRootCA.crt`
3. Проверьте доступ к хосту ClickHouse

### Ошибка API ключа

```
❌ Invalid API key
```

**Решение:**
1. Получите новый ключ: https://console.anthropic.com/
2. Обновите `ANTHROPIC_API_KEY` в `.env`

### Модуль не найден

```
ModuleNotFoundError: No module named 'anthropic'
```

**Решение:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Полезные команды в test_agent.py

- `examples` - показать примеры запросов
- `stats` - статистика по чатам
- `new` - начать новую сессию
- `exit` - выйти

## Следующие шаги

После успешного тестирования:

1. **Запустить API сервер** (для веб-интерфейса):
   ```bash
   python api_server.py
   ```

2. **Настроить автозапуск** (systemd):
   ```bash
   sudo cp agent_service.service /etc/systemd/system/
   sudo systemctl enable agent_service
   sudo systemctl start agent_service
   ```

3. **Интегрировать с фронтенд** - используйте API endpoint:
   ```
   POST http://localhost:8000/api/analyze
   {
     "query": "ваш запрос",
     "session_id": "опционально"
   }
   ```

## Дополнительная информация

- [README.md](README.md) - общая информация о проекте
- [INSTALLATION.md](INSTALLATION.md) - подробная инструкция
- [FULL_IMPLEMENTATION_SPEC.md](FULL_IMPLEMENTATION_SPEC.md) - полная спецификация
