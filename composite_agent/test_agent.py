#!/usr/bin/env python3
"""
Тестовый CLI скрипт для проверки работы CompositeAnalysisAgent.

Запуск:
    cd composite_agent
    python test_agent.py

Или с одиночным запросом:
    python test_agent.py "Покажи структуру таблиц в базе данных"

Для интерактивного диалога просто запустите без аргументов.
"""

import sys
import os
import json
import base64
import argparse
from pathlib import Path

# Убедиться что импорты работают из директории composite_agent
sys.path.insert(0, str(Path(__file__).parent))

from composite_agent import CompositeAnalysisAgent


def save_plot(b64_data: str, index: int, output_dir: Path) -> Path:
    """Сохранить base64 PNG в файл."""
    output_dir.mkdir(exist_ok=True)
    # Убрать data:image/png;base64, prefix
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_data)
    out_path = output_dir / f"plot_{index + 1}.png"
    out_path.write_bytes(img_bytes)
    return out_path


def print_result(result: dict, save_plots: bool = True):
    """Вывести результат агента в консоль."""
    print(f"\n{'═' * 60}")

    if not result["success"]:
        print(f"❌ ОШИБКА: {result.get('error', 'Неизвестная ошибка')}")
        return

    # Лог вызовов инструментов
    if result.get("tool_calls"):
        print("🔧 Вызовы инструментов:")
        for call in result["tool_calls"]:
            tool_input_preview = json.dumps(call["input"], ensure_ascii=False)[:120]
            print(f"  [{call['iteration']}] {call['tool']}: {tool_input_preview}")
        print()

    # Текстовый ответ
    print("🤖 ОТВЕТ АГЕНТА:")
    print("─" * 60)
    print(result.get("text_output", ""))

    # Графики
    plots = result.get("plots", [])
    if plots:
        print(f"\n📊 Графики: {len(plots)} шт.")
        if save_plots:
            plots_dir = Path(__file__).parent / "output_plots"
            for i, plot_data in enumerate(plots):
                out_path = save_plot(plot_data, i, plots_dir)
                print(f"  💾 Сохранён: {out_path}")
    print(f"{'═' * 60}\n")


def run_interactive(agent: CompositeAnalysisAgent, session_id: str | None = None):
    """Интерактивный диалог в терминале."""
    print("=" * 60)
    print("  ClickHouse + Python Analysis Agent")
    print("  Введите 'exit' или 'выход' для завершения")
    print("  Введите 'new' для начала новой сессии")
    print("=" * 60)

    current_session = session_id

    while True:
        try:
            prompt = input("\n❓ Ваш запрос: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nЗавершение.")
            break

        if not prompt:
            continue

        if prompt.lower() in ("exit", "quit", "q", "выход"):
            print("До свидания!")
            break

        if prompt.lower() == "new":
            current_session = None
            print("✅ Начата новая сессия")
            continue

        try:
            print("\n⏳ Обрабатываю запрос...")
            result = agent.analyze(prompt, current_session)
            current_session = result.get("session_id", current_session)
            print_result(result)
        except Exception as e:
            import traceback
            print(f"\n❌ Ошибка: {e}")
            traceback.print_exc()


def run_single_query(agent: CompositeAnalysisAgent, query: str):
    """Выполнить одиночный запрос и выйти."""
    print(f"\n📝 Запрос: {query}")
    print("⏳ Обрабатываю...")
    result = agent.analyze(query)
    print_result(result)

    # Вернуть код ошибки если агент не справился
    return 0 if result["success"] else 1


def main():
    parser = argparse.ArgumentParser(
        description="Тест CompositeAnalysisAgent (ClickHouse + Python)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python test_agent.py
      → интерактивный диалог

  python test_agent.py "Покажи структуру таблиц"
      → одиночный запрос

  python test_agent.py --session abc123 "Какие данные за прошлый месяц?"
      → одиночный запрос в существующей сессии
        """,
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Запрос для агента. Если не указан — интерактивный режим.",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="ID сессии для продолжения диалога",
    )
    args = parser.parse_args()

    # Инициализация агента
    try:
        agent = CompositeAnalysisAgent()
        print("✅ Агент инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации агента: {e}")
        print("\nПроверьте:")
        print("  1. Файл .env создан и заполнен (cp .env.example .env)")
        print("  2. ANTHROPIC_API_KEY задан")
        print("  3. CLICKHOUSE_* параметры заданы")
        sys.exit(1)

    if args.query:
        exit_code = run_single_query(agent, args.query)
        sys.exit(exit_code)
    else:
        run_interactive(agent, session_id=args.session)


if __name__ == "__main__":
    main()
