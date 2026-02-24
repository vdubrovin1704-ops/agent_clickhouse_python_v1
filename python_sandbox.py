"""
Безопасное выполнение Python-кода с захватом графиков matplotlib
Объединяет механизм exec() + parquet из CLI агента и захват графиков из Julius
"""
import io
import base64
import contextlib
import traceback
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # ОБЯЗАТЕЛЬНО для серверного рендеринга
import matplotlib.pyplot as plt
import seaborn as sns

# Настройки matplotlib/seaborn
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['figure.dpi'] = 100
plt.rcParams['font.size'] = 12


class PythonSandbox:
    """Выполнение Python кода с данными из Parquet и захватом графиков"""

    def execute(self, code: str, parquet_path: str) -> dict:
        """
        Выполнить Python код с данными из Parquet.
        Возвращает dict с результатами (НЕ JSON-строку).
        """
        try:
            # ШАГ 1: Загрузить данные из Parquet в DataFrame
            df = pd.read_parquet(parquet_path)
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "result": None,
                "plots": [],
                "error": f"Ошибка загрузки parquet: {str(e)}",
            }

        # ШАГ 2: Подготовить пространство имён для exec()
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
            # ШАГ 3: Выполнить код с перехватом stdout/stderr
            with contextlib.redirect_stdout(stdout_capture), \
                 contextlib.redirect_stderr(stderr_capture):
                exec(code, {"__builtins__": __builtins__}, local_vars)

            # ШАГ 4: Захватить все matplotlib фигуры
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

            # ШАГ 5: Получить result
            result_value = local_vars.get("result")
            if isinstance(result_value, pd.DataFrame):
                result_value = result_value.to_markdown(index=False)
            elif result_value is not None:
                result_value = str(result_value)

            return {
                "success": True,
                "output": stdout_capture.getvalue(),
                "result": result_value,
                "plots": plots,
                "error": None,
            }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            return {
                "success": False,
                "output": stdout_capture.getvalue(),
                "result": None,
                "plots": [],
                "error": error_msg,
            }

        finally:
            # ОБЯЗАТЕЛЬНО очистить matplotlib и переменные
            plt.close('all')
            plt.clf()
            local_vars.clear()
