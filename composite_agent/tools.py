"""
Определения tools для Claude (JSON Schema).
Три инструмента: list_tables, clickhouse_query, python_analysis.
"""

TOOLS_LIST = [
    {
        "name": "list_tables",
        "description": (
            "Получить список всех таблиц в базе данных ClickHouse "
            "с их колонками и типами данных. "
            "Вызови этот инструмент ПЕРВЫМ чтобы узнать структуру данных. "
            "Не вызывай повторно если уже знаешь структуру из контекста диалога."
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
                    "description": "SQL SELECT запрос для ClickHouse",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "python_analysis",
        "description": (
            "Выполнить Python код для анализа и визуализации данных, "
            "полученных из ClickHouse. "
            "Данные уже загружены из parquet и доступны как pandas DataFrame "
            "в переменной `df`. НЕ НУЖНО вызывать pd.read_parquet() — "
            "df уже готов к использованию. "
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
                    "description": (
                        "Python код для выполнения. Переменная df уже содержит DataFrame "
                        "с данными из ClickHouse. Не вызывай read_parquet()."
                    ),
                },
                "parquet_path": {
                    "type": "string",
                    "description": (
                        "Путь к parquet файлу с данными (получен из результата clickhouse_query, "
                        "поле parquet_path). Передай его точно как получил."
                    ),
                },
            },
            "required": ["code", "parquet_path"],
        },
    },
]
