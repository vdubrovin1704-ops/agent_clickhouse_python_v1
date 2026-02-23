# Спецификация: CLI-агент ClickHouse → Parquet → Python Analysis

## ОБЗОР

Простой агент для командной строки Ubuntu. 
Работает в интерактивном режиме: пользователь пишет запрос → агент извлекает данные из ClickHouse в Parquet → выполняет Python-код → выводит результат в терминал.

Это **минимальный прототип** для проверки всей цепочки:
`Запрос → Claude → SQL → ClickHouse → Parquet → Python exec → вывод`

## СТЕК

- Python 3.11+
- Anthropic SDK (anthropic) — Claude Sonnet 4.6, native tool_use
- clickhouse-connect — прямое подключение к ClickHouse
- pandas + pyarrow — работа с данными и Parquet
- Без FastAPI, без SQLite, без истории чатов — чистый CLI

## СТРУКТУРА ФАЙЛОВ

```
cli_agent/
├── .env                  # ANTHROPIC_API_KEY, CLICKHOUSE_*
├── .env.example
├── requirements.txt
├── cli_agent.py          # Единственный файл — весь агент
└── temp_data/            # Временные parquet файлы
```

## .env.example

```
ANTHROPIC_API_KEY=sk-ant-...
CLICKHOUSE_HOST=your-host.mdb.yandexcloud.net
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=your_user
CLICKHOUSE_PASSWORD=your_password
CLICKHOUSE_DATABASE=your_database
CLICKHOUSE_SSL_CERT_PATH=YandexInternalRootCA.crt
```

## requirements.txt

```
anthropic>=0.40.0
clickhouse-connect>=0.7.0
pandas>=2.0.0
numpy>=1.24.0
pyarrow>=14.0.0
python-dotenv>=1.0.0
tabulate>=0.9.0
```

## ФАЙЛ: cli_agent.py — ПОЛНАЯ РЕАЛИЗАЦИЯ

Один файл. Содержит всё: конфигурацию, ClickHouse клиент, Python sandbox, tools, агентный цикл, CLI интерфейс.

### Структура файла:

```
cli_agent.py
│
├── Импорты и загрузка .env
├── Конфигурация (из .env)
├── Класс ClickHouseClient
│   ├── __init__() — подключение к ClickHouse
│   ├── list_tables() → list[dict]
│   └── execute_query(sql) → dict (с сохранением в Parquet)
├── Функция execute_python_code(code, parquet_path) → dict
├── TOOLS — определения tools для Claude (JSON Schema)
├── SYSTEM_PROMPT — инструкции для Claude
├── Функция run_agent(prompt) — агентный цикл tool_use
└── main() — интерактивный CLI
```

---

### БЛОК 1: Импорты и конфигурация

```python
#!/usr/bin/env python3
"""
CLI-агент: ClickHouse → Parquet → Python Analysis
Интерактивный режим в терминале Ubuntu.
"""

import os
import io
import sys
import json
import time
import base64
import hashlib
import traceback
import contextlib
from pathlib import Path

import anthropic
import clickhouse_connect
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Загрузка .env
load_dotenv(Path(__file__).parent / ".env")

# Конфигурация
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192

CLICKHOUSE_HOST = os.environ["CLICKHOUSE_HOST"].replace("https://", "").replace("http://", "")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8443"))
CLICKHOUSE_USER = os.environ["CLICKHOUSE_USER"]
CLICKHOUSE_PASSWORD = os.environ["CLICKHOUSE_PASSWORD"]
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")

# SSL сертификат
CLICKHOUSE_SSL_CERT = ""
ssl_path = os.environ.get("CLICKHOUSE_SSL_CERT_PATH", "")
if ssl_path:
    cert = Path(ssl_path)
    if not cert.is_absolute():
        cert = Path(__file__).parent / cert
    if cert.exists():
        CLICKHOUSE_SSL_CERT = str(cert.resolve())
        print(f"✅ SSL сертификат: {cert.resolve()}")

# Директория для временных parquet файлов
TEMP_DIR = Path(__file__).parent / "temp_data"
TEMP_DIR.mkdir(exist_ok=True)
```

---

### БЛОК 2: Класс ClickHouseClient

```python
class ClickHouseClient:
    """Прямое подключение к ClickHouse"""

    def __init__(self):
        connect_kwargs = {
            "host": CLICKHOUSE_HOST,
            "port": CLICKHOUSE_PORT,
            "username": CLICKHOUSE_USER,
            "password": CLICKHOUSE_PASSWORD,
            "database": CLICKHOUSE_DATABASE,
            "secure": True,
        }
        if CLICKHOUSE_SSL_CERT:
            connect_kwargs["verify"] = True
            connect_kwargs["ca_cert"] = CLICKHOUSE_SSL_CERT
        else:
            connect_kwargs["verify"] = False

        self.client = clickhouse_connect.get_client(**connect_kwargs)
        print(f"✅ ClickHouse подключён: {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DATABASE}")

    def list_tables(self) -> str:
        """Получить список таблиц с колонками и типами. Возвращает JSON-строку."""
        result = self.client.query(
            "SELECT table, name, type "
            "FROM system.columns "
            "WHERE database = currentDatabase() "
            "ORDER BY table, position"
        )
        tables = {}
        for row in result.result_rows:
            table_name, col_name, col_type = row[0], row[1], row[2]
            if table_name not in tables:
                tables[table_name] = []
            tables[table_name].append({"name": col_name, "type": col_type})

        output = [{"table": t, "columns": cols} for t, cols in tables.items()]
        return json.dumps(output, ensure_ascii=False, indent=2)

    def execute_query(self, sql: str) -> str:
        """
        Выполнить SELECT запрос.
        Сохранить результат в Parquet.
        Вернуть JSON-строку с метаданными и путём к parquet.
        """
        # Проверка: только SELECT
        sql_stripped = sql.strip()
        if not sql_stripped.upper().startswith("SELECT"):
            return json.dumps({
                "success": False,
                "error": "Разрешены только SELECT запросы"
            })

        # Добавить LIMIT если нет
        if "LIMIT" not in sql_stripped.upper():
            sql_stripped = f"{sql_stripped.rstrip().rstrip(';')} LIMIT 50000"

        try:
            result = self.client.query(sql_stripped)

            # Создать DataFrame
            df = pd.DataFrame(result.result_rows, columns=result.column_names)

            # Сохранить в Parquet
            query_hash = hashlib.md5(sql_stripped.encode()).hexdigest()[:10]
            parquet_filename = f"query_{query_hash}_{int(time.time())}.parquet"
            parquet_path = str(TEMP_DIR / parquet_filename)
            df.to_parquet(parquet_path, engine="pyarrow", index=False)

            # Превью — первые 5 строк
            preview = df.head(5).to_dict(orient="records")
            # Конвертация сложных типов для JSON
            for row in preview:
                for k, v in row.items():
                    if isinstance(v, (list, dict, set, tuple, np.ndarray)):
                        row[k] = str(v)
                    elif isinstance(v, (np.integer,)):
                        row[k] = int(v)
                    elif isinstance(v, (np.floating,)):
                        row[k] = float(v) if not np.isnan(v) else None
                    elif pd.isna(v):
                        row[k] = None

            return json.dumps({
                "success": True,
                "row_count": len(df),
                "columns": list(df.columns),
                "dtypes": {col: str(df[col].dtype) for col in df.columns},
                "preview_first_5_rows": preview,
                "parquet_path": parquet_path,
            }, ensure_ascii=False, default=str)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "sql": sql_stripped,
            })
```

**ВАЖНО: execute_query() возвращает JSON-строку**, а не dict. Это потому что tool_result в Anthropic API — строка.

**ВАЖНО: parquet_path** — это абсолютный или относительный путь к файлу на диске. Claude получает этот путь и передаёт его в `python_analysis` tool.

---

### БЛОК 3: Функция execute_python_code

```python
def execute_python_code(code: str, parquet_path: str) -> str:
    """
    Выполнить Python код с данными из Parquet.
    
    ПРОЦЕСС:
    1. Загружает parquet_path в DataFrame → переменная `df`
    2. Предоставляет df, pd, np в пространстве имён
    3. Выполняет exec(code)
    4. Захватывает stdout (print)
    5. Захватывает переменную `result` (финальный вывод)
    6. Возвращает JSON-строку с результатами
    
    Claude НЕ ЗНАЕТ про Parquet. Claude пишет код, работающий с `df`.
    Загрузка Parquet → df происходит ЗДЕСЬ, до exec().
    """
    try:
        # ШАГ 1: Загрузить данные из Parquet в DataFrame
        df = pd.read_parquet(parquet_path)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Ошибка загрузки parquet: {str(e)}",
            "parquet_path": parquet_path,
        })

    # ШАГ 2: Подготовить пространство имён для exec()
    local_vars = {
        "df": df,        # ← Claude пишет код с этой переменной
        "pd": pd,
        "np": np,
        "result": None,  # ← Claude устанавливает для финального вывода
    }

    stdout_capture = io.StringIO()

    try:
        # ШАГ 3: Выполнить код с перехватом stdout
        with contextlib.redirect_stdout(stdout_capture):
            exec(code, {"__builtins__": __builtins__}, local_vars)

        # ШАГ 4: Получить result
        result_value = local_vars.get("result")
        if isinstance(result_value, pd.DataFrame):
            result_value = result_value.to_markdown(index=False)
        elif result_value is not None:
            result_value = str(result_value)

        return json.dumps({
            "success": True,
            "output": stdout_capture.getvalue(),
            "result": result_value,
            "error": None,
        }, ensure_ascii=False, default=str)

    except Exception as e:
        return json.dumps({
            "success": False,
            "output": stdout_capture.getvalue(),
            "result": None,
            "error": f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
        })
    finally:
        local_vars.clear()
```

**Ключевой момент**: строка `df = pd.read_parquet(parquet_path)` — это МОСТ между Parquet-файлом и переменной `df`, которую видит Claude. Claude пишет `df.head()`, `df.describe()`, а sandbox загружает данные из Parquet в `df` перед exec().

---

### БЛОК 4: Определения Tools

```python
TOOLS = [
    {
        "name": "list_tables",
        "description": (
            "Получить список всех таблиц в базе данных ClickHouse "
            "с их колонками и типами данных. "
            "Вызови этот инструмент ПЕРВЫМ чтобы узнать структуру данных."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "clickhouse_query",
        "description": (
            "Выполнить SELECT SQL запрос к ClickHouse. "
            "Возвращает количество строк, список колонок, типы данных, "
            "превью первых 5 строк, и путь к parquet-файлу с полными данными. "
            "ПРАВИЛА: "
            "1. Только SELECT запросы. "
            "2. Всегда добавляй LIMIT (обычно 1000-50000). "
            "3. Делай агрегации в SQL (GROUP BY, SUM, COUNT) — ClickHouse быстр."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL SELECT запрос для ClickHouse",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "python_analysis",
        "description": (
            "Выполнить Python код для анализа данных из ClickHouse. "
            "Данные уже загружены из parquet и доступны как pandas DataFrame "
            "в переменной `df`. НЕ НУЖНО вызывать pd.read_parquet() — "
            "df уже готов к использованию. "
            "Доступны: pandas (pd), numpy (np). "
            "Установи переменную `result` для финального текстового вывода. "
            "Используй print() для логирования шагов."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python код. Переменная df уже содержит DataFrame "
                        "с данными из ClickHouse. Не вызывай read_parquet()."
                    ),
                },
                "parquet_path": {
                    "type": "string",
                    "description": (
                        "Путь к parquet файлу (получен из результата clickhouse_query, "
                        "поле parquet_path). Передай его точно как получил."
                    ),
                },
            },
            "required": ["code", "parquet_path"],
        },
    },
]
```

**ОБРАТИ ВНИМАНИЕ** на description `python_analysis`: явно написано "Данные уже загружены из parquet и доступны как DataFrame `df`. НЕ НУЖНО вызывать pd.read_parquet()". Это предотвращает случаи когда Claude пытается сам читать parquet.

---

### БЛОК 5: System Prompt

```python
SYSTEM_PROMPT = """Ты — аналитик данных, работающий с ClickHouse через терминал.

## Процесс работы:

1. ИЗУЧИ СТРУКТУРУ — вызови `list_tables` чтобы увидеть таблицы и колонки
2. ВЫГРУЗИ ДАННЫЕ — напиши SQL через `clickhouse_query`
3. ПРОАНАЛИЗИРУЙ — вызови `python_analysis` чтобы обработать данные

## Правила SQL:
- Только SELECT запросы
- Добавляй LIMIT (1000-50000)
- Делай агрегации в SQL (GROUP BY, SUM, AVG)
- Для типов Array — используй arrayJoin()

## Правила Python:
- Переменная `df` уже содержит DataFrame — НЕ вызывай pd.read_parquet()
- Устанавливай `result` для финального вывода
- Используй print() для шагов
- Форматируй числа: f"{value:,.0f}"

## Для первого запроса в сессии:
ОБЯЗАТЕЛЬНО сначала вызови `list_tables` чтобы узнать структуру данных.

## Язык: русский
"""
```

---

### БЛОК 6: Агентный цикл — функция run_agent

```python
def run_agent(prompt: str, client: anthropic.Anthropic, ch: ClickHouseClient) -> None:
    """
    Выполнить один запрос пользователя через агентный цикл tool_use.
    Результат печатается в stdout.
    """
    messages = [{"role": "user", "content": prompt}]
    max_iterations = 10

    for iteration in range(max_iterations):
        print(f"\n{'─' * 40} Итерация {iteration + 1} {'─' * 40}")

        # Вызов Claude
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        print(f"stop_reason: {response.stop_reason}")

        # ─── Claude закончил ───
        if response.stop_reason == "end_turn":
            print(f"\n{'═' * 60}")
            print("🤖 ОТВЕТ CLAUDE:")
            print(f"{'═' * 60}\n")
            for block in response.content:
                if block.type == "text":
                    print(block.text)
            return

        # ─── Claude хочет вызвать tool ───
        elif response.stop_reason == "tool_use":
            # Добавить ответ ассистента в messages
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    if block.text.strip():
                        print(f"\n💭 Claude думает: {block.text[:200]}")
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            # Выполнить tools и собрать результаты
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    print(f"\n🔧 Tool: {tool_name}")

                    # Показать параметры
                    if tool_name == "clickhouse_query":
                        print(f"   SQL: {tool_input.get('sql', '')[:200]}")
                    elif tool_name == "python_analysis":
                        print(f"   parquet: {tool_input.get('parquet_path', '')}")
                        code_preview = tool_input.get("code", "")[:300]
                        print(f"   code:\n{code_preview}...")

                    # Выполнить tool
                    if tool_name == "list_tables":
                        tool_result_str = ch.list_tables()
                    elif tool_name == "clickhouse_query":
                        tool_result_str = ch.execute_query(tool_input["sql"])
                    elif tool_name == "python_analysis":
                        tool_result_str = execute_python_code(
                            code=tool_input["code"],
                            parquet_path=tool_input["parquet_path"],
                        )
                    else:
                        tool_result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})

                    # Показать результат (превью)
                    try:
                        result_preview = json.loads(tool_result_str)
                        if tool_name == "clickhouse_query" and result_preview.get("success"):
                            print(f"   ✅ Получено строк: {result_preview.get('row_count')}")
                            print(f"   📁 Parquet: {result_preview.get('parquet_path')}")
                        elif tool_name == "python_analysis" and result_preview.get("success"):
                            output = result_preview.get("output", "")
                            if output:
                                print(f"   📝 stdout:\n{output[:500]}")
                            result_val = result_preview.get("result", "")
                            if result_val:
                                print(f"   📊 result:\n{result_val[:500]}")
                        elif not result_preview.get("success", True):
                            print(f"   ❌ Ошибка: {result_preview.get('error', '')[:300]}")
                    except:
                        print(f"   Результат: {tool_result_str[:200]}")

                    # Добавить результат для Claude
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result_str,
                    })

            # Добавить tool results в messages
            messages.append({"role": "user", "content": tool_results})

        else:
            print(f"⚠️ Неожиданный stop_reason: {response.stop_reason}")
            return

    print("❌ Превышен лимит итераций (10)")
```

---

### БЛОК 7: main() — интерактивный CLI

```python
def main():
    print("=" * 60)
    print("  ClickHouse Analysis Agent (CLI)")
    print(f"  Model: {MODEL}")
    print("=" * 60)

    # Инициализация
    try:
        api_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        ch_client = ClickHouseClient()
    except Exception as e:
        print(f"\n❌ Ошибка инициализации: {e}")
        sys.exit(1)

    print(f"\n💬 Введите запрос. 'exit' или 'выход' для завершения.\n")

    while True:
        try:
            prompt = input("❓ Ваш запрос: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nЗавершение.")
            break

        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit", "q", "выход"):
            print("До свидания!")
            break

        try:
            run_agent(prompt, api_client, ch_client)
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            traceback.print_exc()

        print()


if __name__ == "__main__":
    main()
```

---

## ПРИМЕР РАБОТЫ В ТЕРМИНАЛЕ

```
$ python cli_agent.py

============================================================
  ClickHouse Analysis Agent (CLI)
  Model: claude-sonnet-4-6
============================================================
✅ SSL сертификат: /root/cli_agent/YandexInternalRootCA.crt
✅ ClickHouse подключён: rc1a-xxx.mdb.yandexcloud.net:8443/mydb

💬 Введите запрос. 'exit' или 'выход' для завершения.

❓ Ваш запрос: покажи первые 5 строк из таблицы orders

──────────────────── Итерация 1 ────────────────────
stop_reason: tool_use

🔧 Tool: list_tables
   ✅ (получена схема таблиц)

──────────────────── Итерация 2 ────────────────────
stop_reason: tool_use

💭 Claude думает: Я вижу таблицу orders. Выгружу первые строки...

🔧 Tool: clickhouse_query
   SQL: SELECT * FROM orders LIMIT 5
   ✅ Получено строк: 5
   📁 Parquet: ./temp_data/query_a1b2c3d4e5_1708700000.parquet

──────────────────── Итерация 3 ────────────────────
stop_reason: tool_use

🔧 Tool: python_analysis
   parquet: ./temp_data/query_a1b2c3d4e5_1708700000.parquet
   code:
print("📋 Первые 5 строк таблицы orders:")
print(f"Размер: {df.shape[0]} строк × {df.shape[1]} колонок")
print()
print(df.to_markdown(index=False))

result = f"Таблица orders содержит {df.shape[1]} колонок: {', '.join(df.columns)}"...
   📝 stdout:
📋 Первые 5 строк таблицы orders:
Размер: 5 строк × 6 колонок

| id | date       | product  | revenue | quantity | tags          |
|----|------------|----------|---------|----------|---------------|
| 1  | 2025-01-05 | Widget A | 1234.50 | 10       | [sale, promo] |
| 2  | 2025-01-06 | Widget B | 2345.00 | 20       | [new]         |
| 3  | 2025-01-07 | Gadget X | 3456.75 | 5        | [premium]     |
| 4  | 2025-01-08 | Part Y   | 456.00  | 100      | []            |
| 5  | 2025-01-09 | Kit Z    | 5678.25 | 3        | [bundle]      |

   📊 result:
Таблица orders содержит 6 колонок: id, date, product, revenue, quantity, tags

──────────────────── Итерация 4 ────────────────────
stop_reason: end_turn

════════════════════════════════════════════════════
🤖 ОТВЕТ CLAUDE:
════════════════════════════════════════════════════

Вот первые 5 строк таблицы `orders`:

Таблица содержит 6 колонок:
- **id** — идентификатор заказа
- **date** — дата заказа
- **product** — название товара
- **revenue** — выручка
- **quantity** — количество
- **tags** — теги (массив строк)

Обратите внимание, что колонка `tags` содержит массивы — это типичный тип данных ClickHouse.

❓ Ваш запрос:
```

## УСТАНОВКА И ЗАПУСК

```bash
# 1. Создать директорию
mkdir cli_agent && cd cli_agent

# 2. Создать venv
python3 -m venv venv
source venv/bin/activate

# 3. Установить зависимости
pip install anthropic clickhouse-connect pandas numpy pyarrow python-dotenv tabulate

# 4. Скопировать .env
cp .env.example .env
# Заполнить .env своими данными

# 5. Скачать SSL сертификат (для Яндекс Cloud)
wget https://storage.yandexcloud.net/cloud-certs/CA.pem -O YandexInternalRootCA.crt

# 6. Создать директорию для parquet
mkdir -p temp_data

# 7. Запустить
python cli_agent.py
```

## КЛЮЧЕВЫЕ МОМЕНТЫ РЕАЛИЗАЦИИ

### Как Parquet превращается в df:

```
clickhouse_query()                    python_analysis()
       │                                     │
       │  SQL → ClickHouse → DataFrame       │  code + parquet_path
       │  DataFrame → df.to_parquet(path)     │
       │  return {"parquet_path": path}       │  execute_python_code():
       │                                     │    df = pd.read_parquet(path)  ← ВОТ ЗДЕСЬ
       ▼                                     │    local_vars = {'df': df}
  Claude получает path ──────────────────────│    exec(code, local_vars)
  Claude передаёт path в python_analysis ────┘    Claude пишет: df.head()
```

Claude думает что `df` просто существует. Он не знает про Parquet. 
Parquet — деталь реализации sandbox'а, невидимая для Claude.

### Почему Parquet а не передача данных через tool_result:

1. Данные могут быть большими (50000 строк) — не влезут в tool_result
2. tool_result = JSON строка — ограничен по размеру
3. Parquet сохраняет типы (Array, Map, DateTime)
4. Claude получает только preview (5 строк) — этого достаточно чтобы написать код
5. Полные данные остаются на диске, exec() читает их через pd.read_parquet()