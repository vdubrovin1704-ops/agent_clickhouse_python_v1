# Спецификация: Комплексный ИИ-агент ClickHouse + Python Analysis

## 1. ОБЗОР ПРОЕКТА

### Что нужно создать
Единый ИИ-агент, который:
1. Принимает текстовый запрос пользователя через FastAPI REST API
2. Обращается к базе данных ClickHouse (Яндекс Cloud) — выгружает нужные данные
3. Анализирует данные с помощью Python-кода (pandas, matplotlib, seaborn)
4. Возвращает пользователю: текстовый ответ (Markdown), графики (base64 PNG), таблицы
5. Поддерживает историю диалога через session_id

### Стек технологий
- **Python 3.11+**
- **LLM**: Claude Sonnet 4.6 (`claude-sonnet-4-6-20250514`) через **Anthropic SDK** (НЕ OpenRouter, НЕ LangChain, НЕ Claude Agent SDK)
- **Механизм**: Anthropic Messages API с **native tool_use** (Claude сам решает какие tools вызвать)
- **ClickHouse**: подключение через `clickhouse-connect` напрямую (НЕ через MCP)
- **Формат данных**: Parquet (для сохранения сложных типов — Array, Map, и т.д.)
- **API**: FastAPI + uvicorn
- **Хранение чатов**: SQLite (один файл, скользящее окно, автоочистка)
- **Графики**: matplotlib + seaborn → base64 PNG

### Чего НЕ нужно
- НЕ использовать LangChain, LangGraph
- НЕ использовать Claude Agent SDK (claude-agent-sdk)
- НЕ использовать OpenRouter
- НЕ использовать MCP (mcp-clickhouse)
- НЕ загружать CSV/Excel файлы от пользователя (данные ТОЛЬКО из ClickHouse)

---

## 2. СТРУКТУРА ФАЙЛОВ

```
project/
├── .env                        # Конфигурация (ANTHROPIC_API_KEY, CLICKHOUSE_*)
├── .env.example                # Шаблон конфигурации
├── .gitignore
├── requirements.txt            # Зависимости
├── api_server.py               # FastAPI сервер — HTTP endpoints
├── composite_agent.py          # Главный агент — цикл tool_use
├── clickhouse_client.py        # Клиент ClickHouse (прямое подключение)
├── python_sandbox.py           # Выполнение Python-кода (exec с захватом графиков)
├── chat_storage.py             # SQLite хранилище истории чатов
├── tools.py                    # Определения tools для Claude (JSON Schema)
├── config.py                   # Загрузка конфигурации из .env
├── setup.sh                    # Скрипт установки
├── chat_history.db             # SQLite база (создаётся автоматически)
└── temp_data/                  # Временные parquet файлы (автоочистка)
```

---

## 3. КОНФИГУРАЦИЯ

### .env.example
```
# Anthropic API (напрямую, БЕЗ OpenRouter)
ANTHROPIC_API_KEY=sk-ant-...

# ClickHouse (Яндекс Cloud)
CLICKHOUSE_HOST=your-host.mdb.yandexcloud.net
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=your_user
CLICKHOUSE_PASSWORD=your_password
CLICKHOUSE_DATABASE=your_database
CLICKHOUSE_SSL_CERT_PATH=YandexInternalRootCA.crt

# Сервер
SERVER_URL=https://server.asktab.ru
```

### requirements.txt
```
anthropic>=0.40.0
clickhouse-connect>=0.7.0
pandas>=2.0.0
numpy>=1.24.0
pyarrow>=14.0.0
matplotlib>=3.7.0
seaborn>=0.12.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-dotenv>=1.0.0
pydantic>=2.0.0
tabulate>=0.9.0
```

---

## 4. ФАЙЛ: config.py

Загружает и валидирует конфигурацию из .env.

```python
import os
import socket
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Anthropic
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-4-6-20250514"
MAX_TOKENS = 8192

# ClickHouse
CLICKHOUSE_HOST = os.environ["CLICKHOUSE_HOST"].replace("https://", "").replace("http://", "")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8443"))
CLICKHOUSE_USER = os.environ["CLICKHOUSE_USER"]
CLICKHOUSE_PASSWORD = os.environ["CLICKHOUSE_PASSWORD"]
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")

# SSL — поиск сертификата
CLICKHOUSE_SSL_CERT = ""
ssl_setting = os.environ.get("CLICKHOUSE_SSL_CERT_PATH", "")
if ssl_setting:
    cert = Path(ssl_setting)
    if not cert.is_absolute():
        cert = Path(__file__).parent / cert
    if cert.exists():
        CLICKHOUSE_SSL_CERT = str(cert.resolve())

# Пути
TEMP_DIR = Path("./temp_data")
TEMP_DIR.mkdir(exist_ok=True)

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")
```

---

## 5. ФАЙЛ: clickhouse_client.py

Прямое подключение к ClickHouse. Выгрузка данных в Parquet.

### Класс ClickHouseClient

**Методы:**
- `list_tables() -> list[dict]` — список таблиц с колонками и типами
- `execute_query(sql: str, limit: int = 50000) -> dict` — выполнить SELECT, сохранить в Parquet

**list_tables():**
- SQL: `SELECT table, name, type FROM system.columns WHERE database = currentDatabase() ORDER BY table, position`
- Возвращает: `[{"table": "orders", "columns": [{"name": "id", "type": "UInt64"}, ...]}, ...]`

**execute_query(sql):**
- Проверка: только SELECT (starts with "SELECT" case-insensitive)
- Добавление LIMIT если нет: если в SQL нет слова LIMIT, добавить `LIMIT {limit}` в конец
- Выполняет SQL через `clickhouse_connect`
- Создаёт DataFrame из результата
- Сохраняет в Parquet: `temp_data/query_{md5(sql)[:10]}_{timestamp}.parquet`
- Возвращает:
```json
{
  "success": true,
  "row_count": 1234,
  "columns": ["col1", "col2"],
  "dtypes": {"col1": "int64", "col2": "object"},
  "preview": [{"col1": 1, "col2": "abc"}, ...],  // первые 5 строк
  "parquet_path": "./temp_data/query_abc123_1708700000.parquet"
}
```
- Превью: `df.head(5).to_dict(orient='records')` — конвертировать сложные типы (list, dict, NaN) в строки для JSON-сериализации
- При ошибке SQL: возвращает `{"success": false, "error": "текст ошибки"}`

**Подключение к ClickHouse:**
```python
import clickhouse_connect

client = clickhouse_connect.get_client(
    host=CLICKHOUSE_HOST,
    port=CLICKHOUSE_PORT,
    username=CLICKHOUSE_USER,
    password=CLICKHOUSE_PASSWORD,
    database=CLICKHOUSE_DATABASE,
    secure=True,
    verify=bool(CLICKHOUSE_SSL_CERT),
    ca_cert=CLICKHOUSE_SSL_CERT or None,
)
```

---

## 6. ФАЙЛ: python_sandbox.py

Безопасное выполнение Python-кода с захватом графиков.

**ВАЖНО**: Этот код основан на Julius_v2 `execute_python_code()`, но адаптирован для Parquet.

### Класс PythonSandbox

**Метод execute(code: str, parquet_path: str) -> dict:**

1. Загружает данные: `df = pd.read_parquet(parquet_path)`
2. Создаёт namespace для exec:
```python
local_vars = {
    'df': df,
    'pd': pd,
    'np': np,
    'plt': plt,
    'sns': sns,
    'result': None,   # агент устанавливает для финального вывода
}
```
3. Перехватывает stdout: `contextlib.redirect_stdout(StringIO())`
4. Выполняет: `exec(code, {"__builtins__": __builtins__}, local_vars)`
5. Захватывает ВСЕ matplotlib фигуры:
```python
for fig_num in plt.get_fignums():
    fig = plt.figure(fig_num)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('utf-8')
    plots.append(f"data:image/png;base64,{b64}")
```
6. Получает `result` из local_vars — если это DataFrame, конвертирует в Markdown таблицу (`df.to_markdown()`)
7. **ОБЯЗАТЕЛЬНО**: `plt.close('all')` и `local_vars.clear()` в finally

**Возвращает:**
```json
{
  "success": true,
  "output": "ШАГ 1: Загружено 1000 строк...\n...",
  "result": "## Таблица\n| col1 | col2 |\n|...",
  "plots": ["data:image/png;base64,..."],
  "error": null
}
```

При ошибке:
```json
{
  "success": false,
  "output": "...",
  "result": null,
  "plots": [],
  "error": "ValueError: column 'xxx' not found\nTraceback..."
}
```

**Настройки matplotlib/seaborn (выполнить при импорте модуля):**
```python
import matplotlib
matplotlib.use('Agg')  # ОБЯЗАТЕЛЬНО для серверного рендеринга
import matplotlib.pyplot as plt
import seaborn as sns
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['figure.dpi'] = 100
plt.rcParams['font.size'] = 12
```

---

## 7. ФАЙЛ: chat_storage.py

SQLite хранилище для истории чатов.

### Класс ChatStorage

**Параметры конструктора:**
- `db_path: str = "./chat_history.db"`
- `max_messages_per_session: int = 20` — скользящее окно (хранить только последние N)
- `session_ttl_hours: int = 24` — время жизни сессии

**Таблицы SQLite:**
```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT (datetime('now')),
    last_activity TEXT DEFAULT (datetime('now'))
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_msg_session ON messages(session_id, created_at);
```

**Включить WAL mode**: `PRAGMA journal_mode=WAL;`

**Методы:**

- `save_user_message(session_id: str, text: str)` — сохранить сообщение пользователя
- `save_assistant_message(session_id: str, text: str)` — сохранить ответ (ТОЛЬКО текст, без base64 графиков). Если text > 3000 символов — обрезать с пометкой "[...обрезано...]"
- `get_history(session_id: str) -> list[dict]` — получить историю в формате `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- `cleanup_expired()` — удалить сессии старше TTL. Вызывается периодически (раз в 30 минут)
- `get_stats() -> dict` — `{"active_sessions": N, "total_messages": M, "db_size_mb": X}`

**Скользящее окно:**
После каждого insert — удалить лишние сообщения:
```sql
DELETE FROM messages 
WHERE session_id = ? AND id NOT IN (
    SELECT id FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?
)
```

---

## 8. ФАЙЛ: tools.py

Определения tools для Claude (JSON Schema).

### Три tool'а:

**Tool 1: list_tables**
```python
{
    "name": "list_tables",
    "description": (
        "Получить список всех таблиц в базе данных ClickHouse "
        "с их колонками и типами данных. "
        "ОБЯЗАТЕЛЬНО в��зови этот инструмент ПЕРВЫМ при первом запросе в сессии, "
        "чтобы узнать какие данные доступны. "
        "Не вызывай повторно если уже знаешь структуру из контекста диалога."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}
```

**Tool 2: clickhouse_query**
```python
{
    "name": "clickhouse_query",
    "description": (
        "Выполнить SELECT SQL запрос к базе данных ClickHouse. "
        "Возвращает: количество строк, список колонок, типы данных, "
        "превью первых 5 строк, и путь к parquet-файлу с полными данными. "
        "ПРАВИЛА: "
        "1. Только SELECT запросы (INSERT/UPDATE/DELETE запрещены). "
        "2. ВСЕГДА добавляй разумный LIMIT (обычно 1000-50000). "
        "3. Делай агрегации и фильтрации В САМОМ SQL — ClickHouse очень быстр для этого. "
        "4. Для колонок типа Array — используй arrayJoin() если нужно развернуть. "
        "5. Для больших таблиц — сначала узнай COUNT(*), потом выгружай с LIMIT."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "SQL SELECT запрос для ClickHouse"
            }
        },
        "required": ["sql"]
    }
}
```

**Tool 3: python_analysis**
```python
{
    "name": "python_analysis",
    "description": (
        "Выполнить Python код для анализа и визуализации данных, "
        "полученных из ClickHouse. "
        "Данные доступны как pandas DataFrame в переменной `df`. "
        "Доступные библиотеки: pandas (pd), numpy (np), matplotlib.pyplot (plt), seaborn (sns). "
        "ПРАВИЛА КОДА: "
        "1. Устанавливай переменную `result` (строка или DataFrame) для финального текстового вывода. "
        "2. Используй print() для логирования шагов. "
        "3. Для графиков используй plt/sns — все фигуры автоматически захватываются. "
        "4. Подписывай оси графиков и заголовки НА РУССКОМ ЯЗЫКЕ. "
        "5. Форматируй числа: f'{value:,.0f}' для целых, f'{value:,.2f}' для дробных. "
        "6. Для таблиц в result используй Markdown формат. "
        "7. Если данные нужно предобработать (удалить NaN, привести типы) — делай это в коде."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python код для выполнения. Переменная df содержит DataFrame с данными."
            },
            "parquet_path": {
                "type": "string",
                "description": "Путь к parquet файлу с данными (получен из результата clickhouse_query)"
            }
        },
        "required": ["code", "parquet_path"]
    }
}
```

---

## 9. ФАЙЛ: composite_agent.py — ГЛАВНЫЙ АГЕНТ

Это ядро системы. Реализует агентный цикл через Anthropic Messages API с tool_use.

### Класс CompositeAnalysisAgent

**Конструктор:**
```python
def __init__(self):
    self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    self.ch_client = ClickHouseClient()
    self.sandbox = PythonSandbox()
    self.chat_storage = ChatStorage()
```

### SYSTEM PROMPT (обязательно включить):

```
Ты — опытный аналитик данных. Ты работаешь с базой данных ClickHouse и анализируешь данные с помощью Python.

## Твой рабочий процесс:

### Шаг 1: Понимание запроса
Внимательно прочитай запрос пользователя. Определи:
- Какие данные нужны?
- Нужна ли визуализация (график)?
- Нужна ли таблица?
- Нужны ли вычисления/агрегации?

### Шаг 2: Изучение структуры данных
Если ты ещё НЕ знаешь структуру таблиц (первый запрос в сессии) — вызови `list_tables`.
Если структура уже известна из контекста диалога — пропусти этот шаг.

### Шаг 3: Выгрузка данных из ClickHouse
Напиши оптимальный SQL запрос через `clickhouse_query`:
- Делай агрегации (SUM, COUNT, AVG, GROUP BY) В САМОМ SQL — это быстрее
- Фильтруй данные в WHERE — не выгружай лишнее
- Добавляй LIMIT (обычно 1000-10000 для анализа, до 50000 для больших выборок)
- Используй ClickHouse функции: toStartOfMonth(), toYear(), arrayJoin(), и т.д.

### Шаг 4: Анализ и визуализация в Python
Вызови `python_analysis` для:
- Построения графиков (bar, line, pie, scatter, heatmap)
- Создания красивых таблиц
- Дополнительных вычислений (проценты, ранги, тренды)

### Правила Python-кода:
1. ВСЕГДА устанавливай `result` — строку с Markdown для текстового вывода
2. Используй print() для логирования: print("📊 Шаг 1: Загружаю данные...")
3. Подписывай графики: plt.title(), plt.xlabel(), plt.ylabel() — на русском
4. Форматируй числа с разделителями: f"{value:,.0f}"
5. Используй эмодзи в result для красоты: 📊 📈 ✅ 📋

### Шаг 5: Финальный ответ
Сформируй понятный текстовый ответ с выводами и рекомендациями.
НЕ дублируй данные из result — они уже показаны пользователю.
Добавь краткие выводы и интерпретацию.

## Стиль ответа:
- Используй Markdown: заголовки ##, таблицы, списки
- Используй эмодзи для структурирования
- Числа — с разделителями тысяч
- Язык — русский
```

### Главный метод analyze(user_query, session_id) -> dict:

**Алгоритм (ВАЖНО — это агентный цикл с tool_use):**

```python
def analyze(self, user_query: str, session_id: str) -> dict:
    # 1. Сохранить сообщение пользователя в историю
    self.chat_storage.save_user_message(session_id, user_query)
    
    # 2. Получить историю из SQLite
    history = self.chat_storage.get_history(session_id)
    
    # 3. Подготовить messages для Anthropic API
    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # 4. Переменные для сбора результатов
    all_plots = []        # Все графики со всех вызовов python_analysis
    tool_calls_log = []   # Лог вызовов для отладки
    max_iterations = 10   # Защита от бесконечного цикла
    
    # 5. АГЕНТНЫЙ ЦИКЛ
    for iteration in range(max_iterations):
        
        # 5a. Вызов Claude
        response = self.anthropic_client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS_LIST,  # из tools.py
            messages=messages,
        )
        
        # 5b. Если Claude закончил (stop_reason == "end_turn")
        if response.stop_reason == "end_turn":
            # Собрать текстовый ответ
            text_parts = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
            
            final_text = "\n".join(text_parts)
            
            # Сохранить ответ ассистента
            self.chat_storage.save_assistant_message(session_id, final_text)
            
            return {
                "success": True,
                "text_output": final_text,
                "plots": all_plots,
                "tool_calls": tool_calls_log,
                "error": None,
                "session_id": session_id,
            }
        
        # 5c. Если Claude хочет вызвать tool (stop_reason == "tool_use")
        elif response.stop_reason == "tool_use":
            
            # Добавить ответ ассистента в messages (с tool_use блоками)
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            
            messages.append({"role": "assistant", "content": assistant_content})
            
            # Выполнить каждый tool_use и собрать результаты
            tool_results_content = []
            
            for block in response.content:
                if block.type == "tool_use":
                    # Выполнить tool
                    tool_result = self._execute_tool(block.name, block.input)
                    
                    # Если python_analysis — достать графики
                    if block.name == "python_analysis":
                        try:
                            result_data = json.loads(tool_result)
                            if result_data.get("plots"):
                                all_plots.extend(result_data["plots"])
                        except:
                            pass
                    
                    # Логировать
                    tool_calls_log.append({
                        "tool": block.name,
                        "input": block.input,
                        "iteration": iteration,
                    })
                    
                    # Добавить результат для Claude
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result,
                    })
            
            # Добавить результаты tools в messages
            messages.append({"role": "user", "content": tool_results_content})
        
        else:
            # Неожиданный stop_reason
            return {
                "success": False,
                "text_output": "",
                "plots": [],
                "tool_calls": tool_calls_log,
                "error": f"Unexpected stop_reason: {response.stop_reason}",
                "session_id": session_id,
            }
    
    # Если вышли из цикла по лимиту
    return {
        "success": False,
        "text_output": "",
        "plots": all_plots,
        "tool_calls": tool_calls_log,
        "error": "Превышен лимит итераций агента (10)",
        "session_id": session_id,
    }
```

### Метод _execute_tool(tool_name, tool_input) -> str:

```python
def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
    """Выполнить tool и вернуть результат как JSON-строку"""
    try:
        if tool_name == "list_tables":
            tables = self.ch_client.list_tables()
            return json.dumps(tables, ensure_ascii=False, indent=2)
        
        elif tool_name == "clickhouse_query":
            result = self.ch_client.execute_query(tool_input["sql"])
            return json.dumps(result, ensure_ascii=False, default=str)
        
        elif tool_name == "python_analysis":
            result = self.sandbox.execute(
                code=tool_input["code"],
                parquet_path=tool_input["parquet_path"],
            )
            return json.dumps(result, ensure_ascii=False, default=str)
        
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    
    except Exception as e:
        import traceback
        return json.dumps({
            "error": str(e),
            "traceback": traceback.format_exc()
        })
```

---

## 10. ФАЙЛ: api_server.py — FastAPI

### Endpoints:

**GET /**
Health check. Возвращает `{"status": "online", "model": "Claude Sonnet 4.6"}`.

**GET /health**
Health check. Возвращает `{"status": "healthy", "timestamp": "..."}`.

**GET /api/info**
Информация о сервисе. Возвращает features, version, model.

**POST /api/analyze**
Основной endpoint. Принимает JSON:
```json
{
  "query": "Покажи продажи за январь",
  "session_id": "abc-123-def"  // опци��нально, если нет — генерируется uuid
}
```

Возвращает JSON:
```json
{
  "success": true,
  "session_id": "abc-123-def",
  "text_output": "## 📊 Продажи за январь\n\n...",
  "plots": ["data:image/png;base64,..."],
  "tool_calls": [
    {"tool": "list_tables", "input": {}, "iteration": 0},
    {"tool": "clickhouse_query", "input": {"sql": "SELECT ..."}, "iteration": 1},
    {"tool": "python_analysis", "input": {"code": "...", "parquet_path": "..."}, "iteration": 2}
  ],
  "error": null,
  "timestamp": "2026-02-23T12:00:00"
}
```

**GET /api/chat-stats**
Статистика чатов: `{"active_sessions": N, "total_messages": M, "db_size_mb": X}`.

### CORS:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Запуск анализа в thread pool:
```python
result = await asyncio.to_thread(agent.analyze, query, session_id)
```
Это важно потому что `anthropic_client.messages.create()` — синхронный и блокирующий.

### Фоновая задача при startup:
```python
@app.on_event("startup")
async def startup():
    async def cleanup_loop():
        while True:
            await asyncio.sleep(1800)  # каждые 30 минут
            agent.chat_storage.cleanup_expired()
            agent.cleanup_temp_files()  # удалить parquet старше 1 часа
    asyncio.create_task(cleanup_loop())
```

### Метод cleanup_temp_files агента:
Удаляет файлы `temp_data/*.parquet` старше 1 часа:
```python
import time
for f in TEMP_DIR.glob("*.parquet"):
    if f.stat().st_mtime < time.time() - 3600:
        f.unlink()
```

---

## 11. ВАЖНЫЕ ДЕТАЛИ РЕАЛИЗАЦИИ

### 11.1 Обработка ошибок tool_use

Если exec() в python_sandbox упал с ошибкой — **НЕ бросать исключение**.
Вернуть `{"success": false, "error": "..."}` как tool_result.
Claude **увидит ошибку** и **сам исправит код** в следующей итерации цикла.
Это встроенный retry без дополнительной логики.

### 11.2 Размер tool_result

Результат `clickhouse_query` может быть большим (если 50000 строк в preview).
НО: preview — это только 5 строк. Полные данные — в parquet на диске.
Claude получает только preview + parquet_path.

### 11.3 Графики в истории чата

В `save_assistant_message()` сохраняется ТОЛЬКО текст — НЕ base64 графиков.
Графики возвращаются в API response одноразово.
Это предотвращает раздувание SQLite базы.

### 11.4 Parquet vs CSV

Используется Parquet потому что:
- ClickHouse имеет типы Array(String), Map(String, UInt64), и т.д.
- Parquet сохраняет типы нативно
- CSV теряет типы (list становится строкой "[1, 2, 3]")
- Parquet компактнее (сжатие колонок)
- `pd.read_parquet()` быстрее `pd.read_csv()`

### 11.5 Конвертация сложных типов в preview

Перед возвратом preview в JSON нужно конвертировать:
```python
for row in preview:
    for k, v in row.items():
        if isinstance(v, (list, dict, set, tuple)):
            row[k] = str(v)
        elif isinstance(v, (np.integer,)):
            row[k] = int(v)
        elif isinstance(v, (np.floating,)):
            row[k] = float(v)
        elif pd.isna(v):
            row[k] = None
```

### 11.6 SSL подключение к Яндекс Cloud ClickHouse

Сертификат скачивается отдельно:
```bash
wget https://storage.yandexcloud.net/cloud-certs/CA.pem -O YandexInternalRootCA.crt
```

При подключении через clickhouse-connect:
```python
client = clickhouse_connect.get_client(
    secure=True,
    verify=True,
    ca_cert="/path/to/YandexInternalRootCA.crt",
)
```

---

## 12. ПРИМЕР РАБОТЫ АГЕНТА

**Запрос пользователя:** "Покажи топ-10 товаров по выручке за январь 2025 и построй bar chart"

**Итерация 1:** Claude вызывает `list_tables` → получает схему:
```json
[{"table": "orders", "columns": [
  {"name": "date", "type": "Date"},
  {"name": "product_name", "type": "String"},
  {"name": "revenue", "type": "Float64"},
  {"name": "quantity", "type": "UInt32"}
]}]
```

**Итерация 2:** Claude вызывает `clickhouse_query`:
```sql
SELECT product_name, SUM(revenue) as total_revenue, SUM(quantity) as total_qty
FROM orders
WHERE date >= '2025-01-01' AND date < '2025-02-01'
GROUP BY product_name
ORDER BY total_revenue DESC
LIMIT 10
```

**Итерация 3:** Claude вызывает `python_analysis`:
```python
import matplotlib.pyplot as plt
import seaborn as sns

print("📊 Строю график топ-10 товаров...")

# Сортировка для красивого отображения
df_sorted = df.sort_values('total_revenue', ascending=True)

# Bar chart
fig, ax = plt.subplots(figsize=(12, 6))
bars = ax.barh(df_sorted['product_name'], df_sorted['total_revenue'], color='#4CAF50')

# Подписи значений
for bar, value in zip(bars, df_sorted['total_revenue']):
    ax.text(bar.get_width() + bar.get_width()*0.01, bar.get_y() + bar.get_height()/2,
            f'{value:,.0f} ₽', va='center', fontsize=10)

ax.set_xlabel('Выручка, ₽')
ax.set_title('Топ-10 товаров по выручке (Январь 2025)')
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
plt.tight_layout()

# Текстовый результат
total = df['total_revenue'].sum()
result = f"""## 📊 Топ-10 товаров по выручке (Январь 2025)

| # | Товар | Выручка | Кол-во | Доля |
|---|-------|---------|--------|------|
"""
for i, (_, row) in enumerate(df.sort_values('total_revenue', ascending=False).iterrows(), 1):
    share = row['total_revenue'] / total * 100
    result += f"| {i} | {row['product_name']} | {row['total_revenue']:,.0f} ₽ | {row['total_qty']:,.0f} | {share:.1f}% |\n"

result += f"\n**Общая выручка:** {total:,.0f} ₽"
```

**Итерация 4:** Claude формирует финальный ответ (stop_reason: "end_turn"):
```
Анализ показал, что лидером продаж в январе 2025 является Widget Pro 
с выручкой 1,234,567 ₽ (28.3% от общей). Три верхних позиции 
составляют более 60% всей выручки.
```

---

## 13. ДЕПЛОЙ

### setup.sh
```bash
#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
echo "Отредактируйте .env и заполните данные"
```

### Systemd сервис
```ini
[Unit]
Description=ClickHouse Analysis Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/julius_v3
ExecStart=/root/julius_v3/venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/root/julius_v3/.env

[Install]
WantedBy=multi-user.target
```

### Nginx
```nginx
server {
    listen 443 ssl;
    server_name server.asktab.ru;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;  # Важно: агент может работать долго
    }
}
```