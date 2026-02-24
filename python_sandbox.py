import base64
import contextlib
import io
import json
from io import StringIO
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (10, 6)
plt.rcParams["figure.dpi"] = 100
plt.rcParams["font.size"] = 12


class PythonSandbox:
    def execute(self, code: str, parquet_path: str) -> dict[str, Any]:
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as exc:
            return {
                "success": False,
                "output": "",
                "result": None,
                "plots": [],
                "error": f"Ошибка загрузки parquet: {exc}",
            }

        local_vars: dict[str, Any] = {
            "df": df,
            "pd": pd,
            "np": np,
            "plt": plt,
            "sns": sns,
            "result": None,
        }
        stdout_buffer = StringIO()
        stderr_buffer = StringIO()

        try:
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                exec(code, {"__builtins__": __builtins__}, local_vars)

            plots: list[str] = []
            if plt.get_fignums():
                for fig_num in plt.get_fignums():
                    fig = plt.figure(fig_num)
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
                    buf.seek(0)
                    b64 = base64.b64encode(buf.read()).decode("utf-8")
                    plots.append(f"data:image/png;base64,{b64}")
                    buf.close()

            result_value = local_vars.get("result")
            if isinstance(result_value, pd.DataFrame):
                result_value = result_value.to_markdown(index=False)
            elif result_value is not None:
                result_value = str(result_value)

            output_combined = stdout_buffer.getvalue()
            if stderr_buffer.getvalue():
                output_combined = f"{output_combined}{stderr_buffer.getvalue()}"

            return {
                "success": True,
                "output": output_combined,
                "result": result_value,
                "plots": plots,
                "error": None,
            }
        except Exception as exc:
            output_combined = stdout_buffer.getvalue()
            if stderr_buffer.getvalue():
                output_combined = f"{output_combined}{stderr_buffer.getvalue()}"
            return {
                "success": False,
                "output": output_combined,
                "result": None,
                "plots": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
        finally:
            plt.close("all")
            plt.clf()
            local_vars.clear()
