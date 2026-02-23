"""
Прямое подключение к ClickHouse.
Выгрузка данных в Parquet для сохранения сложных типов (Array, Map, и т.д.)
"""

import json
import time
import hashlib

import clickhouse_connect
import pandas as pd
import numpy as np

from config import (
    CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_USER,
    CLICKHOUSE_PASSWORD, CLICKHOUSE_DATABASE, CLICKHOUSE_SSL_CERT,
    TEMP_DIR,
)


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
        # ВАЖНО: если сертификат есть — verify=True + ca_cert
        # если нет — verify=False (позволяет работать без сертификата)
        if CLICKHOUSE_SSL_CERT:
            connect_kwargs["verify"] = True
            connect_kwargs["ca_cert"] = CLICKHOUSE_SSL_CERT
        else:
            connect_kwargs["verify"] = False

        self.client = clickhouse_connect.get_client(**connect_kwargs)

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
        Сохранить результат в Parquet (сохраняет сложные типы ClickHouse).
        Вернуть JSON-строку с метаданными и путём к parquet.
        """
        sql_stripped = sql.strip()

        # Проверка: только SELECT
        if not sql_stripped.upper().startswith("SELECT"):
            return json.dumps({
                "success": False,
                "error": "Разрешены только SELECT запросы",
            })

        # Автоматическое добавление LIMIT если нет
        if "LIMIT" not in sql_stripped.upper():
            sql_stripped = f"{sql_stripped.rstrip().rstrip(';')} LIMIT 50000"

        try:
            result = self.client.query(sql_stripped)

            # Создать DataFrame
            df = pd.DataFrame(result.result_rows, columns=result.column_names)

            # Сохранить в Parquet — сохраняет сложные типы Array/Map
            query_hash = hashlib.md5(sql_stripped.encode()).hexdigest()[:10]
            parquet_filename = f"query_{query_hash}_{int(time.time())}.parquet"
            parquet_path = str(TEMP_DIR / parquet_filename)
            df.to_parquet(parquet_path, engine="pyarrow", index=False)

            # Превью — первые 5 строк с конвертацией сложных типов для JSON
            preview = df.head(5).to_dict(orient="records")
            for row in preview:
                for k, v in row.items():
                    if isinstance(v, (list, dict, set, tuple, np.ndarray)):
                        row[k] = str(v)
                    elif isinstance(v, np.integer):
                        row[k] = int(v)
                    elif isinstance(v, np.floating):
                        row[k] = float(v) if not np.isnan(v) else None
                    else:
                        try:
                            if pd.isna(v):
                                row[k] = None
                        except (TypeError, ValueError):
                            pass

            return json.dumps(
                {
                    "success": True,
                    "row_count": len(df),
                    "columns": list(df.columns),
                    "dtypes": {col: str(df[col].dtype) for col in df.columns},
                    "preview_first_5_rows": preview,
                    "parquet_path": parquet_path,
                },
                ensure_ascii=False,
                default=str,
            )

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "sql": sql_stripped,
            })
