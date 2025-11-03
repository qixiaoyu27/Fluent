"""SU2 结果文件后处理模块。"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Tuple

try:  # pragma: no cover - 测试环境可能缺少 matplotlib
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None  # type: ignore

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)


def _read_history(history_path: Path) -> Tuple[List[int], Dict[str, List[float]]]:
    """读取 SU2 history.csv 并返回迭代步与指标序列。"""

    iterations: List[int] = []
    series: Dict[str, List[float]] = {}

    with history_path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        headers: List[str] = []
        for row in reader:
            if not row:
                continue
            if row[0].startswith("#"):
                continue
            if not headers:
                headers = row
                for head in headers[1:]:
                    series[head] = []
                continue
            iterations.append(int(row[0]))
            for key, value in zip(headers[1:], row[1:]):
                try:
                    series[key].append(float(value))
                except ValueError:
                    series[key].append(float("nan"))
    return iterations, series


def _read_forces(forces_path: Path) -> Dict[str, float]:
    """解析 forces_breakdown.dat 中的最终气动力。"""

    result: Dict[str, float] = {}
    with forces_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            try:
                key, value = line.split()
                result[key] = float(value)
            except ValueError:
                continue
    return result


def _write_summary(output_dir: Path, forces: Dict[str, float], history_last: Dict[str, float]) -> Path:
    """将关键气动指标写入文本报告。"""

    summary_path = output_dir / "post_summary.txt"
    lines = [
        "航模整流罩气动计算摘要",
        "======================",
    ]

    if forces:
        lines.append("\n最终气动力 (forces_breakdown.dat):")
        for key, value in forces.items():
            lines.append(f"  - {key}: {value:.6f}")

    if history_last:
        lines.append("\n迭代历史最后一帧:")
        for key, value in history_last.items():
            lines.append(f"  - {key}: {value:.6f}")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def _plot_history(output_dir: Path, iterations: List[int], series: Dict[str, List[float]], plot_cfg: Dict[str, str]) -> List[Path]:
    """基于 history 数据绘制收敛曲线。"""

    if plt is None:
        LOGGER.warning("未安装 matplotlib，跳过曲线绘制。")
        return []

    output_paths: List[Path] = []

    coeff_plot = plot_cfg.get("coefficient_history")
    if coeff_plot and {"CL", "CD"}.issubset(series.keys()):
        fig, ax = plt.subplots()
        ax.plot(iterations, series["CL"], label="CL")
        ax.plot(iterations, series["CD"], label="CD")
        ax.set_xlabel("迭代步")
        ax.set_ylabel("气动系数")
        ax.set_title("升阻系数收敛曲线")
        ax.grid(True)
        ax.legend()
        coeff_path = output_dir / coeff_plot
        fig.savefig(coeff_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        output_paths.append(coeff_path)

    residual_plot = plot_cfg.get("convergence")
    residual_keys = [key for key in series.keys() if key.startswith("Res_")]
    if residual_plot and residual_keys:
        fig, ax = plt.subplots()
        for key in residual_keys:
            ax.semilogy(iterations, series[key], label=key)
        ax.set_xlabel("迭代步")
        ax.set_ylabel("残差 (对数坐标)")
        ax.set_title("残差收敛历史")
        ax.grid(True, which="both")
        ax.legend()
        residual_path = output_dir / residual_plot
        fig.savefig(residual_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        output_paths.append(residual_path)

    return output_paths


def run_postprocessing(config: Dict, cfd_dir: Path) -> Dict[str, List[Path]]:
    """读取 SU2 输出并生成报告/图表。"""

    post_cfg = config.get("postprocessing", {})
    history_file = post_cfg.get("history_file", "history.csv")
    forces_file = post_cfg.get("forces_file", "forces_breakdown.dat")
    plot_cfg = post_cfg.get("plots", {})

    history_path = cfd_dir / history_file
    forces_path = cfd_dir / forces_file

    artifacts: Dict[str, List[Path]] = {"plots": [], "reports": []}
    history_last: Dict[str, float] = {}

    if history_path.is_file():
        iterations, series = _read_history(history_path)
        if iterations:
            history_last = {key: values[-1] for key, values in series.items() if values}
            artifacts["plots"] = _plot_history(cfd_dir, iterations, series, plot_cfg)
    else:
        LOGGER.warning("未找到 history 文件: %s", history_path)

    forces: Dict[str, float] = {}
    if forces_path.is_file():
        forces = _read_forces(forces_path)
    else:
        LOGGER.warning("未找到 forces_breakdown 文件: %s", forces_path)

    if history_last or forces:
        summary_path = _write_summary(cfd_dir, forces, history_last)
        artifacts.setdefault("reports", []).append(summary_path)

    return artifacts
