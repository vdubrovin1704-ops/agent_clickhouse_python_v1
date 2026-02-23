"""
Безопасное выполнение Python-кода с захватом графиков matplotlib.
"""

import io
import base64
import traceback
import contextlib

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['figure.dpi'] = 100
plt.rcParams['font.size'] = 12

# Restricted builtins: only safe functions needed for data analysis.
# Blocks open(), eval(), exec(), __import__(), compile() to prevent file/code injection.
_BLOCKED_BUILTINS = frozenset({
    "open", "eval", "exec", "compile", "__import__",
    "breakpoint", "exit", "quit", "input",
    "globals", "locals", "vars",
})
_builtins_dict = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
_SAFE_BUILTINS = {k: v for k, v in _builtins_dict.items() if k not in _BLOCKED_BUILTINS}


class PythonSandbox:
    """Выполнение Python-кода с захватом stdout, result и графиков."""

    def execute(self, code: str, parquet_path: str) -> dict:
        """
        Выполнить Python код с данными из Parquet.

        Переменная `df` уже содержит DataFrame.
        Claude пишет код, работающий с `df`.
        """
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

        local_vars = {
            'df': df,
            'pd': pd,
            'np': np,
            'plt': plt,
            'sns': sns,
            'result': None,
        }

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_capture), \
                 contextlib.redirect_stderr(stderr_capture):
                exec(code, {"__builtins__": _SAFE_BUILTINS}, local_vars)

            # Захват графиков
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

            # Получить result
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
            return {
                "success": False,
                "output": stdout_capture.getvalue(),
                "result": None,
                "plots": [],
                "error": f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
            }
        finally:
            plt.close('all')
            local_vars.clear()
