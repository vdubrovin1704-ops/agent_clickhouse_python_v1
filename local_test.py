import argparse
import json

from composite_agent import CompositeAnalysisAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Тестовый запуск агента без API сервера")
    parser.add_argument(
        "--query",
        type=str,
        required=False,
        default="Покажи первые 5 строк любой таблицы и посчитай количество записей",
        help="Запрос пользователя",
    )
    parser.add_argument("--session-id", type=str, default=None, help="Идентификатор сессии (опционально)")
    args = parser.parse_args()

    agent = CompositeAnalysisAgent()
    result = agent.analyze(args.query, args.session_id)

    print("\n=== Результат ===")
    print(f"success: {result.get('success')}")
    print(f"session_id: {result.get('session_id')}")
    print("\n--- text_output ---")
    print(result.get("text_output", ""))
    print("\n--- plots count ---")
    print(len(result.get("plots", [])))
    print("\n--- tool_calls ---")
    print(json.dumps(result.get("tool_calls", []), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
