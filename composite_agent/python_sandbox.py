"""
Безопасное выполнение Python-кода с захватом stdout и matplotlib-графиков.
Объединяет exec-механизм из CLI-агента и захват графиков из Julius_v2.
"""

import io
import base64
import traceback
import contextlib

import matplotlib
matplotlib.use('Agg')  # ОБЯЗАТЕЛЬНО для серверного рендеринга (без дисплея)
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

# Глобальные настройки matplotlib/seaborn
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['figure.dpi'] = 100
plt.rcParams['font.size'] = 12


class PythonSandbox:
    """Безопасное выполнение Python-кода с захватом графиков"""

    def execute(self, code: str, parquet_path: str) -> dict:
        """
        Выполнить Python-код с данными из Parquet.

        1. Загружает parquet_path → DataFrame (df)
        2. Предоставляет df, pd, np, plt, sns в namespace
        3. Перехватывает stdout/stderr
        4. Выполняет exec(code)
        5. Захватывает все matplotlib-фигуры → base64 PNG
        6. Возвращает dict (НЕ JSON-строку) с результатами

        Claude пишет код, работающий с переменной df.
        Загрузка parquet → df происходит здесь, до exec().
        """
        # Загрузить данные из Parquet
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "result": None,
                "plots": [],
                "error": f"Ошибка загрузки parquet: {str(e)}",
            }

        # Namespace для exec — df уже готов, Claude не вызывает read_parquet()
        local_vars = {
            "df": df,
            "pd": pd,
            "np": np,
            "plt": plt,
            "sns": sns,
            "result": None,
        }

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_capture), \
                 contextlib.redirect_stderr(stderr_capture):
                exec(code, {"__builtins__": __builtins__}, local_vars)  # noqa: S102

            # Получить финальный result
            result_value = local_vars.get("result")
            if isinstance(result_value, pd.DataFrame):
                result_value = result_value.to_markdown(index=False)
            elif result_value is not None:
                result_value = str(result_value)

            # Захватить все matplotlib-фигуры → base64 PNG (из Julius_v2, dpi=150)
            plots = []
            if plt.get_fignums():
                for fig_num in plt.get_fignums():
                    fig = plt.figure(fig_num)
                    buf = io.BytesIO()
                    fig.savefig(buf, format='png', bbox_inches='tight', dpi=150)
                    buf.seek(0)
                    b64 = base64.b64encode(buf.read()).decode('utf-8')
                    plots.append(f"data:image/png;base64,{b64}")
                    buf.close()

            output = stdout_capture.getvalue()
            stderr_out = stderr_capture.getvalue()
            if stderr_out:
                output = output + ("\n[stderr]\n" + stderr_out if output else "[stderr]\n" + stderr_out)

            return {
                "success": True,
                "output": output,
                "result": result_value,
                "plots": plots,
                "error": None,
            }

        except Exception as e:
            return {
                "success": False,
                "output": stdout_capture.getvalue(),
                "result": None,
                "plots": [],
                "error": f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
            }

        finally:
            # ОБЯЗАТЕЛЬНО — освободить ресурсы matplotlib
            plt.close('all')
            plt.clf()
            local_vars.clear()
