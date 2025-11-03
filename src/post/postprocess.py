"""SU2 仿真结果后处理模块

默认读取 SU2 输出的 history.csv 与 surface_flow.csv，
利用 pandas 与 matplotlib 生成收敛曲线和关键气动系数统计。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import matplotlib.pyplot as plt
import pandas as pd


@dataclass
class PostConfig:
    """后处理阶段所需的文件路径配置。"""

    report_json: Path
    plot_image: Path
    summary_txt: Path

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PostConfig":
        return cls(
            report_json=Path(data.get("report_json", "result/cfd/post_report.json")),
            plot_image=Path(data.get("plot_image", "result/cfd/convergence.png")),
            summary_txt=Path(data.get("summary_txt", "result/cfd/summary.txt")),
        )


@dataclass
class CFDResult:
    """与后处理耦合所需的 CFD 输出配置。"""

    history_output: Path
    surface_output: Path


@dataclass
class Summary:
    """后处理统计结果。"""

    cl: float | None
    cd: float | None
    cm: float | None
    iterations: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "CL": self.cl,
            "CD": self.cd,
            "CM": self.cm,
            "Iterations": self.iterations,
        }


def _load_history(history_file: Path) -> pd.DataFrame:
    """加载 SU2 输出的 history.csv。"""

    if not history_file.exists():
        raise FileNotFoundError(f"未找到收敛历史文件: {history_file}")
    return pd.read_csv(history_file)


def _load_surface(surface_file: Path) -> pd.DataFrame:
    """加载 SU2 输出的 surface_flow.csv。"""

    if not surface_file.exists():
        raise FileNotFoundError(f"未找到表面气动数据: {surface_file}")
    return pd.read_csv(surface_file)


def _plot_convergence(history: pd.DataFrame, output: Path) -> None:
    """绘制残差收敛曲线。"""

    output.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 4.5), dpi=150)
    for column in [col for col in history.columns if "RESIDUAL" in col.upper()]:
        plt.semilogy(history[column], label=column)
    plt.xlabel("迭代步")
    plt.ylabel("残差 (log)")
    plt.title("SU2 残差收敛曲线")
    plt.grid(True, which="both", linestyle="--", linewidth=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output, bbox_inches="tight")
    plt.close()


def _extract_coefficients(surface: pd.DataFrame) -> Summary:
    """从 surface_flow.csv 中提取 CL/CD/CM。"""

    grouped = surface.groupby("Marker") if "Marker" in surface.columns else {"ALL": surface}
    total_cl = total_cd = total_cm = 0.0

    for _, df in grouped.items() if isinstance(grouped, dict) else grouped:
        total_cl += df.get("CL", 0.0).sum()
        total_cd += df.get("CD", 0.0).sum()
        total_cm += df.get("CMz", df.get("CM", 0.0)).sum()

    cl = total_cl if total_cl else None
    cd = total_cd if total_cd else None
    cm = total_cm if total_cm else None

    iterations = int(surface["Iter"].max()) if "Iter" in surface.columns else len(surface)

    return Summary(cl=cl, cd=cd, cm=cm, iterations=iterations)


def _write_summary(summary: Summary, config: PostConfig) -> None:
    """输出 JSON/TXT 形式的摘要报告。"""

    config.report_json.parent.mkdir(parents=True, exist_ok=True)
    config.summary_txt.parent.mkdir(parents=True, exist_ok=True)

    config.report_json.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["SU2 气动系数摘要", "================", ""]
    if summary.cl is not None:
        lines.append(f"升力系数 CL: {summary.cl:.6f}")
    if summary.cd is not None:
        lines.append(f"阻力系数 CD: {summary.cd:.6f}")
    if summary.cm is not None:
        lines.append(f"俯仰力矩系数 CM: {summary.cm:.6f}")
    lines.append(f"迭代步数: {summary.iterations}")

    config.summary_txt.write_text("\n".join(lines), encoding="utf-8")


def run(config: PostConfig, cfd_cfg: CFDResult | Any) -> Dict[str, Any]:
    """执行后处理流程。"""

    history = _load_history(cfd_cfg.history_output)
    surface = _load_surface(cfd_cfg.surface_output)

    _plot_convergence(history, config.plot_image)
    summary = _extract_coefficients(surface)
    _write_summary(summary, config)

    return summary.to_dict()
