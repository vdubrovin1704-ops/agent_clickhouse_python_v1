#!/usr/bin/env python3
"""
Тестовый файл для проверки работы комплексного агента
ClickHouse + Python Analysis
"""
import os
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Загрузка .env
load_dotenv()

# Проверка наличия необходимых переменных
required_vars = ["ANTHROPIC_API_KEY", "CLICKHOUSE_HOST", "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    print(f"❌ Ошибка: не заданы переменные окружения: {', '.join(missing_vars)}")
    print("Отредактируйте файл .env и заполните необходимые данные")
    sys.exit(1)

from composite_agent import CompositeAnalysisAgent


def print_separator(title=""):
    """Печать разделителя"""
    if title:
        print(f"\n{'═' * 60}")
        print(f"  {title}")
        print(f"{'═' * 60}\n")
    else:
        print(f"{'─' * 60}\n")


def test_agent():
    """Тестирование агента в интерактивном режиме"""
    print_separator("Тестирование комплексного агента")
    print("📊 Агент: ClickHouse + Python Analysis")
    print("🤖 Модель: Claude Sonnet 4")
    print_separator()

    # Инициализация агента
    try:
        agent = CompositeAnalysisAgent()
        print("✅ Агент успешно инициализирован\n")
    except Exception as e:
        print(f"❌ Ошибка инициализации агента: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Генерация session_id
    session_id = str(uuid.uuid4())
    print(f"📝 ID сессии: {session_id}\n")
    print_separator()

    # Примеры тестовых запросов
    example_queries = [
        "Покажи список всех таблиц в базе данных",
        "Выгрузи первые 10 записей из любой таблицы",
        "Покажи статистику по данным: количество записей, основные показатели",
    ]

    print("💡 Примеры запросов:")
    for i, query in enumerate(example_queries, 1):
        print(f"   {i}. {query}")
    print()
    print_separator()

    # Интерактивный режим
    print("💬 Введите запрос (или 'exit' для выхода, 'examples' для примеров)")
    print()

    query_count = 0

    while True:
        try:
            user_query = input("❓ Ваш запрос: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Завершение работы...")
            break

        if not user_query:
            continue

        if user_query.lower() in ("exit", "quit", "q", "выход"):
            print("👋 До свидания!")
            break

        if user_query.lower() == "examples":
            print("\n💡 Примеры запросов:")
            for i, query in enumerate(example_queries, 1):
                print(f"   {i}. {query}")
            print()
            continue

        if user_query.lower() == "stats":
            stats = agent.chat_storage.get_stats()
            print(f"\n📊 Статистика:")
            print(f"   Активных сессий: {stats['active_sessions']}")
            print(f"   Всего сообщений: {stats['total_messages']}")
            print(f"   Размер БД: {stats['db_size_mb']} МБ\n")
            continue

        if user_query.lower() == "new":
            session_id = str(uuid.uuid4())
            print(f"\n🆕 Новая сессия: {session_id}\n")
            continue

        # Выполнение запроса
        query_count += 1
        print_separator(f"Запрос #{query_count}")

        try:
            result = agent.analyze(user_query, session_id)

            if result["success"]:
                # Текстовый ответ
                print("\n🤖 Ответ агента:")
                print_separator()
                print(result["text_output"])
                print_separator()

                # Графики
                if result["plots"]:
                    print(f"\n📊 Создано графиков: {len(result['plots'])}")
                    print("   (графики в формате base64 доступны в result['plots'])")

                    # Сохранение графиков в HTML для просмотра
                    if query_count == 1:  # Только для первого запроса
                        save_plots = input("\n💾 Сохранить графики в HTML для просмотра? (y/n): ").strip().lower()
                        if save_plots == 'y':
                            html_content = generate_plots_html(result["plots"], user_query)
                            html_path = f"plots_session_{session_id[:8]}.html"
                            with open(html_path, "w", encoding="utf-8") as f:
                                f.write(html_content)
                            print(f"✅ Графики сохранены в {html_path}")
                            print(f"   Откройте файл в браузере для просмотра")

                # Информация о вызовах tools
                if result["tool_calls"]:
                    print(f"\n🔧 Выполнено инструментов: {len(result['tool_calls'])}")
                    for i, call in enumerate(result["tool_calls"], 1):
                        print(f"   {i}. {call['tool']} (итерация {call['iteration']})")

            else:
                print(f"\n❌ Ошибка: {result['error']}")

        except Exception as e:
            print(f"\n❌ Произошла ошибка: {e}")
            import traceback
            traceback.print_exc()

        print_separator()


def generate_plots_html(plots: list, query: str) -> str:
    """Генерация HTML страницы с графиками"""
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Графики - {query[:50]}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .plot {{
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .plot img {{
            max-width: 100%;
            height: auto;
        }}
        .info {{
            background: #e3f2fd;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <h1>📊 Результаты анализа</h1>
    <div class="info">
        <strong>Запрос:</strong> {query}
    </div>
"""

    for i, plot in enumerate(plots, 1):
        html += f"""
    <div class="plot">
        <h3>График {i}</h3>
        <img src="{plot}" alt="График {i}">
    </div>
"""

    html += """
</body>
</html>
"""
    return html


def main():
    """Главная функция"""
    test_agent()


if __name__ == "__main__":
    main()
