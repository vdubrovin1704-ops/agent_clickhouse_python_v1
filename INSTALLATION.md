# Инструкция по установке и запуску агента на Ubuntu

## Описание проекта

Комплексный ИИ-агент, который объединяет:
- **ClickHouse агент** - выгрузка данных из базы данных ClickHouse
- **Python Analysis агент** - анализ данных, построение графиков и таблиц

Агент работает следующим образом:
1. Пользователь пишет запрос на естественном языке
2. Агент выгружает необходимые данные из ClickHouse в формате Parquet
3. Агент анализирует данные с помощью Python кода (pandas, matplotlib, seaborn)
4. Агент строит графики и таблицы
5. Агент выдает результат пользователю

## Требования

- **ОС**: Ubuntu 20.04+ (или любая Linux система с Python 3.11+)
- **Python**: 3.11 или выше
- **ClickHouse**: подключение к базе данных ClickHouse (Яндекс Cloud)
- **API ключ**: Anthropic API ключ для Claude Sonnet 4

## Установка

### Шаг 1: Клонирование репозитория

```bash
cd /root
git clone https://github.com/vdubrovin1704-ops/agent_clickhouse_python_v1.git
cd agent_clickhouse_python_v1
```

### Шаг 2: Установка Python зависимостей

```bash
# Создание виртуального окружения
python3 -m venv venv

# Активация виртуального окружения
source venv/bin/activate

# Обновление pip
pip install --upgrade pip

# Установка зависимостей
pip install -r requirements.txt
```

### Шаг 3: Скачивание SSL сертификата для ClickHouse (Яндекс Cloud)

```bash
# Скачать сертификат
wget -q https://storage.yandexcloud.net/cloud-certs/CA.pem -O YandexInternalRootCA.crt

# Проверить что файл скачался
ls -lh YandexInternalRootCA.crt
```

### Шаг 4: Настройка конфигурации

```bash
# Копировать шаблон конфигурации
cp .env.example .env

# Отредактировать конфигурацию
nano .env
```

**Заполните следующие переменные в файле `.env`:**

```bash
# Anthropic API (получить на https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-api03-ваш-ключ-здесь

# ClickHouse (Яндекс Cloud)
CLICKHOUSE_HOST=ваш-хост.mdb.yandexcloud.net
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=ваш_пользователь
CLICKHOUSE_PASSWORD=ваш_пароль
CLICKHOUSE_DATABASE=ваша_база_данных
CLICKHOUSE_SSL_CERT_PATH=YandexInternalRootCA.crt

# Сервер (опционально, для будущего API)
SERVER_URL=https://server.asktab.ru
```

**Сохраните файл**: `Ctrl+O`, затем `Ctrl+X`

## Запуск агента для тестирования

### Тестовый запуск (интерактивный режим)

```bash
# Активировать виртуальное окружение (если не активировано)
source venv/bin/activate

# Запустить тестовый файл
python test_agent.py
```

### Примеры запросов для тестирования

После запуска `test_agent.py` вы можете вводить запросы на русском языке:

1. **Просмотр структуры базы данных:**
   ```
   Покажи список всех таблиц в базе данных
   ```

2. **Выгрузка данных:**
   ```
   Выгрузи первые 100 записей из таблицы orders
   ```

3. **Анализ с графиками:**
   ```
   Покажи топ-10 товаров по выручке за последний месяц и построй bar chart
   ```

4. **Агрегация данных:**
   ```
   Посчитай общую выручку по месяцам за 2024 год и построй line chart
   ```

### Специальные команды в интерактивном режиме

- `exit` или `выход` - завершить работу
- `examples` - показать примеры запросов
- `stats` - показать статистику по чатам
- `new` - начать новую сессию

## Структура проекта

```
agent_clickhouse_python_v1/
├── .env                        # Конфигурация (не в git)
├── .env.example                # Шаблон конфигурации
├── .gitignore                  # Игнорируемые файлы
├── requirements.txt            # Python зависимости
├── config.py                   # Загрузка конфигурации
├── clickhouse_client.py        # Клиент ClickHouse
├── python_sandbox.py           # Выполнение Python кода
├── chat_storage.py             # Хранилище истории чатов (SQLite)
├── tools.py                    # Определения tools для Claude
├── composite_agent.py          # Главный агент
├── test_agent.py               # Тестовый файл для проверки
├── chat_history.db             # SQLite база (создаётся автоматически)
└── temp_data/                  # Временные parquet файлы (создаётся автоматически)
```

## Как работает агент

### Архитектура

Агент использует **Anthropic Messages API** с нативным механизмом **tool_use**:

1. **Пользователь** отправляет запрос
2. **Claude Sonnet 4** анализирует запрос и решает какие инструменты (tools) нужно вызвать
3. **Агент** выполняет вызовы tools:
   - `list_tables` - получить список таблиц в ClickHouse
   - `clickhouse_query` - выполнить SQL запрос и выгрузить данные в Parquet
   - `python_analysis` - выполнить Python код для анализа данных
4. **Claude** получает результаты и формирует ответ пользователю
5. **История диалога** сохраняется в SQLite

### Формат данных: Parquet

Агент использует **Parquet** вместо CSV потому что:
- ClickHouse имеет сложные типы данных: `Array(String)`, `Map(String, UInt64)`, и т.д.
- Parquet сохраняет типы данных нативно
- CSV теряет типы (массив становится строкой "[1, 2, 3]")
- Parquet компактнее благодаря сжатию
- `pd.read_parquet()` быстрее чем `pd.read_csv()`

### История диалога

- История сохраняется в **SQLite** (`chat_history.db`)
- Для каждой сессии хранится **скользящее окно** последних 20 сообщений
- Старые сессии (> 24 часов неактивности) автоматически удаляются
- Графики в историю НЕ сохраняются (только текст)

### Графики

- Графики создаются с помощью **matplotlib** и **seaborn**
- Автоматически захватываются все созданные фигуры
- Возвращаются в формате **base64 PNG**
- Можно сохранить в HTML файл для просмотра в браузере

## Устранение проблем

### Ошибка подключения к ClickHouse

```
❌ Ошибка: Could not connect to ClickHouse
```

**Решение:**
1. Проверьте правильность данных в `.env` (хост, порт, пользователь, пароль)
2. Проверьте что файл `YandexInternalRootCA.crt` существует
3. Проверьте сетевое подключение к ClickHouse

### Ошибка API ключа Anthropic

```
❌ Ошибка: Invalid API key
```

**Решение:**
1. Проверьте что `ANTHROPIC_API_KEY` в `.env` корректный
2. Получите новый ключ на https://console.anthropic.com/

### Ошибки с Python зависимостями

```
ModuleNotFoundError: No module named 'anthropic'
```

**Решение:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Следующие шаги

После успешного тестирования агента вы можете:

1. **Создать FastAPI сервер** (api_server.py) для работы через HTTP API
2. **Интегрировать с фронтенд** (веб-интерфейс для общения с агентом)
3. **Настроить systemd сервис** для автозапуска
4. **Настроить nginx** для проксирования запросов

## Примеры использования из Python кода

```python
from composite_agent import CompositeAnalysisAgent
import uuid

# Создать агент
agent = CompositeAnalysisAgent()

# Создать сессию
session_id = str(uuid.uuid4())

# Выполнить запрос
result = agent.analyze(
    user_query="Покажи топ-10 товаров по выручке",
    session_id=session_id
)

# Получить результат
if result["success"]:
    print(result["text_output"])  # Текстовый ответ
    print(f"Графиков: {len(result['plots'])}")  # Количество графиков
else:
    print(f"Ошибка: {result['error']}")
```

## Контакты и поддержка

Если у вас возникли вопросы или проблемы:
- Создайте Issue в GitHub репозитории
- Проверьте логи для диагностики проблем

## Лицензия

Этот проект создан для внутреннего использования.
