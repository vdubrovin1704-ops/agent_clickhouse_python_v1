import json
import time
import uuid
from typing import Any, Dict, List

import anthropic

from chat_storage import ChatStorage
from clickhouse_client import ClickHouseClient
from config import ANTHROPIC_API_KEY, MAX_TOKENS, MODEL, TEMP_DIR
from python_sandbox import PythonSandbox
from tools import TOOLS_LIST


SYSTEM_PROMPT = """Ты — опытный аналитик данных. Ты работаешь с базой данных ClickHouse и анализируешь данные с помощью Python.

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
1. Переменная `df` уже содержит DataFrame — НЕ вызывай pd.read_parquet()
2. ВСЕГДА устанавливай `result` — строку с Markdown для текстового вывода
3. Используй print() для логирования: print("📊 Шаг 1: Загружаю данные...")
4. Подписывай графики: plt.title(), plt.xlabel(), plt.ylabel() — на русском
5. Форматируй числа с разделителями: f"{value:,.0f}"
6. Используй эмодзи в result для красоты: 📊 📈 ✅ 📋

### Шаг 5: Финальный ответ
Сформируй понятный текстовый ответ с выводами и рекомендациями.
НЕ дублируй данные из result — они уже показаны пользователю.
Добавь краткие выводы и интерпретацию.

## Стиль ответа:
- Используй Markdown: заголовки ##, таблицы, списки
- Используй эмодзи для структурирования
- Числа — с разделителями тысяч
- Язык — русский
"""


class CompositeAnalysisAgent:
    def __init__(self) -> None:
        self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.ch_client = ClickHouseClient()
        self.sandbox = PythonSandbox()
        self.chat_storage = ChatStorage()

    def analyze(self, user_query: str, session_id: str | None = None) -> Dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        user_query = user_query.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")

        self.chat_storage.save_user_message(session_id, user_query)
        history = self.chat_storage.get_history(session_id)

        messages: List[Dict[str, Any]] = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        all_plots: List[str] = []
        tool_calls_log: List[Dict[str, Any]] = []
        max_iterations = 10

        for iteration in range(max_iterations):
            response = self.anthropic_client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOLS_LIST,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                text_parts: List[str] = []
                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)

                final_text = "\n".join(text_parts)
                self.chat_storage.save_assistant_message(session_id, final_text)

                return {
                    "success": True,
                    "text_output": final_text,
                    "plots": all_plots,
                    "tool_calls": tool_calls_log,
                    "error": None,
                    "session_id": session_id,
                }

            if response.stop_reason == "tool_use":
                assistant_content: List[Dict[str, Any]] = []
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                messages.append({"role": "assistant", "content": assistant_content})

                tool_results_content: List[Dict[str, Any]] = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_result = self._execute_tool(block.name, block.input)
                    tool_result = tool_result.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")

                    if block.name == "python_analysis":
                        try:
                            parsed = json.loads(tool_result)
                            if parsed.get("plots"):
                                all_plots.extend(parsed["plots"])
                                sanitized = {k: v for k, v in parsed.items() if k != "plots"}
                                sanitized["plots_count"] = len(parsed["plots"])
                                tool_result = json.dumps(sanitized, ensure_ascii=False, default=str)
                        except Exception:
                            pass

                    tool_calls_log.append(
                        {
                            "tool": block.name,
                            "input": block.input,
                            "iteration": iteration,
                        }
                    )

                    tool_results_content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result,
                        }
                    )

                messages.append({"role": "user", "content": tool_results_content})
                continue

            return {
                "success": False,
                "text_output": "",
                "plots": [],
                "tool_calls": tool_calls_log,
                "error": f"Unexpected stop_reason: {response.stop_reason}",
                "session_id": session_id,
            }

        return {
            "success": False,
            "text_output": "",
            "plots": all_plots,
            "tool_calls": tool_calls_log,
            "error": "Превышен лимит итераций агента (10)",
            "session_id": session_id,
        }

    def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        try:
            if tool_name == "list_tables":
                return self.ch_client.list_tables()
            if tool_name == "clickhouse_query":
                return self.ch_client.execute_query(tool_input["sql"])
            if tool_name == "python_analysis":
                result = self.sandbox.execute(code=tool_input["code"], parquet_path=tool_input["parquet_path"])
                return json.dumps(result, ensure_ascii=False, default=str)
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as exc:
            return json.dumps(
                {
                    "error": str(exc),
                }
            )

    def cleanup_temp_files(self, older_than_seconds: int = 3600) -> None:
        threshold = time.time() - older_than_seconds
        for file_path in TEMP_DIR.glob("*.parquet"):
            try:
                if file_path.stat().st_mtime < threshold:
                    file_path.unlink()
            except FileNotFoundError:
                continue
