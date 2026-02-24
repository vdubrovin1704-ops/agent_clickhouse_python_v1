"""
Главный комплексный агент: ClickHouse + Python Analysis
Реализует агентный цикл через Anthropic Messages API с tool_use
"""
import json
import time
import traceback
from pathlib import Path
import anthropic
from config import ANTHROPIC_API_KEY, MODEL, MAX_TOKENS, TEMP_DIR
from clickhouse_client import ClickHouseClient
from python_sandbox import PythonSandbox
from chat_storage import ChatStorage
from tools import TOOLS, SYSTEM_PROMPT


class CompositeAnalysisAgent:
    """
    Главный агент, объединяющий:
    - ClickHouse для выгрузки данных
    - Python Sandbox для анализа и графиков
    - Историю диалога через SQLite
    """

    def __init__(self):
        self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.ch_client = ClickHouseClient()
        self.sandbox = PythonSandbox()
        self.chat_storage = ChatStorage()

    def analyze(self, user_query: str, session_id: str) -> dict:
        """
        Выполнить анализ по запросу пользователя.
        Возвращает dict с результатами.
        """
        # 0. Sanitize input (предотвращает UTF-8 ошибки)
        user_query = user_query.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')

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

        # 5. АГЕНТНЫЙ ЦИКЛ (из рабочего CLI агента)
        for iteration in range(max_iterations):

            # 5a. Вызов Claude
            try:
                response = self.anthropic_client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
            except Exception as e:
                return {
                    "success": False,
                    "text_output": "",
                    "plots": [],
                    "tool_calls": tool_calls_log,
                    "error": f"Ошибка вызова Claude API: {str(e)}",
                    "session_id": session_id,
                }

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

                        # Sanitize tool result (из рабочего CLI агента)
                        tool_result = tool_result.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')

                        # Если python_analysis — достать графики
                        if block.name == "python_analysis":
                            try:
                                result_data = json.loads(tool_result)
                                if result_data.get("plots"):
                                    all_plots.extend(result_data["plots"])
                                    # Убрать plots из tool_result чтобы не раздувать контекст Claude
                                    result_data_for_claude = {k: v for k, v in result_data.items() if k != "plots"}
                                    result_data_for_claude["plots_count"] = len(result_data["plots"])
                                    tool_result = json.dumps(result_data_for_claude, ensure_ascii=False, default=str)
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

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Выполнить tool и вернуть результат как JSON-строку"""
        try:
            if tool_name == "list_tables":
                # list_tables() уже возвращает JSON-строку (как в CLI агенте)
                return self.ch_client.list_tables()

            elif tool_name == "clickhouse_query":
                # execute_query() уже возвращает JSON-строку (как в CLI агенте)
                return self.ch_client.execute_query(tool_input["sql"])

            elif tool_name == "python_analysis":
                result = self.sandbox.execute(
                    code=tool_input["code"],
                    parquet_path=tool_input["parquet_path"],
                )
                # sandbox.execute() возвращает dict, сериализуем в JSON
                return json.dumps(result, ensure_ascii=False, default=str)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            return json.dumps({
                "error": str(e),
                "traceback": traceback.format_exc()
            })

    def cleanup_temp_files(self):
        """Удалить временные parquet файлы старше 1 часа"""
        import time
        for f in TEMP_DIR.glob("*.parquet"):
            if f.stat().st_mtime < time.time() - 3600:
                try:
                    f.unlink()
                except:
                    pass
