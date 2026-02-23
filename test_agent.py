#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы агента в интерактивном режиме (CLI).

Использование:
  1. Заполните .env файл (см. .env.example)
  2. python test_agent.py

Агент подключится к ClickHouse, примет ваш текстовый запрос,
выгрузит нужные данные, проанализирует их с помощью Python и
выведет результат: текст, таблицы, графики (сохранятся в PNG).
"""

import sys
import json
import traceback
from pathlib import Path

from composite_agent import CompositeAnalysisAgent
from config import MODEL


def save_plots(plots: list, output_dir: str = ".") -> list:
    """Сохранить base64 графики в PNG файлы."""
    import base64

    saved = []
    out = Path(output_dir)
    out.mkdir(exist_ok=True)
    for i, plot_b64 in enumerate(plots):
        # Убрать data:image/png;base64, prefix
        data = plot_b64.split(",", 1)[-1]
        filename = out / f"plot_{i + 1}.png"
        filename.write_bytes(base64.b64decode(data))
        saved.append(str(filename))
    return saved


def main():
    print("=" * 60)
    print("  ClickHouse + Python Analysis Agent (TEST CLI)")
    print(f"  Model: {MODEL}")
    print("=" * 60)

    try:
        agent = CompositeAnalysisAgent()
    except Exception as e:
        print(f"\n❌ Ошибка инициализации: {e}")
        traceback.print_exc()
        sys.exit(1)

    print("\n✅ Агент инициализирован.")
    print("💬 Введите запрос. 'exit' или 'выход' для завершения.\n")

    session_id = None  # автосоздаётся при первом запросе

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
            result = agent.analyze(prompt, session_id)
            session_id = result.get("session_id", session_id)

            print(f"\n{'═' * 60}")

            if result["success"]:
                print("🤖 ОТВЕТ АГЕНТА:")
                print(f"{'═' * 60}\n")
                print(result["text_output"])

                # Сохранить графики
                if result.get("plots"):
                    saved = save_plots(result["plots"])
                    print(f"\n📊 Сохранено графиков: {len(saved)}")
                    for path in saved:
                        print(f"   → {path}")

                # Показать tool calls
                if result.get("tool_calls"):
                    print(f"\n🔧 Tool calls ({len(result['tool_calls'])}):")
                    for tc in result["tool_calls"]:
                        tool_input_preview = json.dumps(tc["input"], ensure_ascii=False)
                        if len(tool_input_preview) > 100:
                            tool_input_preview = tool_input_preview[:100] + "..."
                        print(f"   [{tc['iteration']}] {tc['tool']}({tool_input_preview})")
            else:
                print(f"❌ Ошибка: {result.get('error', 'Unknown error')}")

            print()

        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            traceback.print_exc()
            print()


if __name__ == "__main__":
    main()
