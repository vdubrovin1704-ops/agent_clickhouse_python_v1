"""
Главный агент: ClickHouse → Parquet → Python Analysis.
Реализует агентный цикл через Anthropic Messages API с native tool_use.
"""

import json
import time
import traceback
import uuid
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY, MODEL, MAX_TOKENS, TEMP_DIR
from clickhouse_client import ClickHouseClient
from python_sandbox import PythonSandbox
from chat_storage import ChatStorage
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
    """
    Агент, объединяющий ClickHouse-запросы и Python-анализ данных.
    Использует Anthropic Messages API с native tool_use.
    """

    def __init__(self):
        self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.ch_client = ClickHouseClient()
        self.sandbox = PythonSandbox()
        self.chat_storage = ChatStorage(
            db_path=str(Path(__file__).parent / "chat_history.db")
        )

    def analyze(self, user_query: str, session_id: str | None = None) -> dict:
        """
        Выполнить запрос пользователя.

        Args:
            user_query: текстовый запрос
            session_id: ID сессии (генерируется если не передан)

        Returns:
            dict с полями:
              success, session_id, text_output, plots, tool_calls, error
        """
        if not session_id:
            session_id = str(uuid.uuid4())

        # Sanitize input — предотвращает UTF-8 encoding errors в Anthropic API
        user_query = user_query.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')

        # Сохранить сообщение пользователя в историю
        self.chat_storage.save_user_message(session_id, user_query)

        # Получить историю из SQLite → формат messages для Anthropic API
        history = self.chat_storage.get_history(session_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]

        all_plots = []       # Все графики со всех вызовов python_analysis
        tool_calls_log = []  # Лог вызовов для отладки
        max_iterations = 10  # Защита от бесконечного цикла

        for iteration in range(max_iterations):
            # Вызов Claude
            response = self.anthropic_client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOLS_LIST,
                messages=messages,
            )

            # Claude закончил — финальный ответ
            if response.stop_reason == "end_turn":
                text_parts = [
                    block.text
                    for block in response.content
                    if block.type == "text"
                ]
                final_text = "\n".join(text_parts)

                self.chat_storage.save_assistant_message(session_id, final_text)

                return {
                    "success": True,
                    "session_id": session_id,
                    "text_output": final_text,
                    "plots": all_plots,
                    "tool_calls": tool_calls_log,
                    "error": None,
                }

            # Claude хочет вызвать tool
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

                # Выполнить каждый tool и собрать результаты
                tool_results_content = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_result = self._execute_tool(block.name, block.input)

                    # Sanitize — предотвращает encoding errors
                    tool_result = tool_result.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')

                    # Если python_analysis — вынести графики из tool_result
                    # чтобы base64 не раздувал контекст Claude
                    if block.name == "python_analysis":
                        try:
                            result_data = json.loads(tool_result)
                            if result_data.get("plots"):
                                all_plots.extend(result_data["plots"])
                                result_data_for_claude = {
                                    k: v for k, v in result_data.items() if k != "plots"
                                }
                                result_data_for_claude["plots_count"] = len(result_data["plots"])
                                tool_result = json.dumps(result_data_for_claude, ensure_ascii=False, default=str)
                        except Exception:
                            pass

                    tool_calls_log.append({
                        "tool": block.name,
                        "input": block.input,
                        "iteration": iteration,
                    })

                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result,
                    })

                messages.append({"role": "user", "content": tool_results_content})

            else:
                return {
                    "success": False,
                    "session_id": session_id,
                    "text_output": "",
                    "plots": [],
                    "tool_calls": tool_calls_log,
                    "error": f"Unexpected stop_reason: {response.stop_reason}",
                }

        # Превышен лимит итераций
        return {
            "success": False,
            "session_id": session_id,
            "text_output": "",
            "plots": all_plots,
            "tool_calls": tool_calls_log,
            "error": "Превышен лимит итераций агента (10)",
        }

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Выполнить tool и вернуть результат как JSON-строку."""
        try:
            if tool_name == "list_tables":
                return self.ch_client.list_tables()

            elif tool_name == "clickhouse_query":
                return self.ch_client.execute_query(tool_input["sql"])

            elif tool_name == "python_analysis":
                result = self.sandbox.execute(
                    code=tool_input["code"],
                    parquet_path=tool_input["parquet_path"],
                )
                # sandbox.execute() возвращает dict — сериализуем в JSON
                return json.dumps(result, ensure_ascii=False, default=str)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            return json.dumps({
                "error": str(e),
                "traceback": traceback.format_exc(),
            })

    def cleanup_temp_files(self):
        """Удалить parquet файлы старше 1 часа."""
        cutoff = time.time() - 3600
        for f in TEMP_DIR.glob("*.parquet"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except Exception:
                pass
