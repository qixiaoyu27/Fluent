"""后处理模块，使用 Python 原生工具对 SU2 结果进行快速分析。

功能包括：
- 读取 SU2 输出的历史 CSV 文件；
- 计算收敛过程中升阻力系数、残差的统计信息；
- 绘制升力系数/阻力系数迭代曲线以及残差衰减曲线；
- 输出 JSON 摘要文件与 PNG 图表文件，便于报告撰写。

后处理依赖 ``matplotlib``，若环境中未安装，可通过 ``pip install matplotlib`` 获取。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@dataclass
class PostProcessConfig:
    """后处理阶段需要的文件路径配置。"""

    history_summary: str
    plots: Dict[str, str]


def load_config(path: Path = CONFIG_PATH) -> Tuple[PostProcessConfig, Dict[str, Path], Path, Dict]:
    """解析配置文件，返回后处理参数及项目路径。"""

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    post_cfg = PostProcessConfig(**config["postprocess"])
    project_root = Path(path).resolve().parents[1]
    output_dirs = {
        key: project_root / value for key, value in config["project"]["output_dirs"].items()
    }
    for dir_path in output_dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    return post_cfg, output_dirs, project_root, config


def summarize_history(history_path: Path, post_cfg: PostProcessConfig, project_root: Path) -> Path:
    """将 SU2 历史数据统计为 JSON。"""

    df = pd.read_csv(history_path)
    summary = {
        "iterations": int(df.shape[0]),
        "cl_mean": float(df["CL"].mean()) if "CL" in df.columns else None,
        "cd_mean": float(df["CD"].mean()) if "CD" in df.columns else None,
        "cl_last": float(df["CL"].iloc[-1]) if "CL" in df.columns else None,
        "cd_last": float(df["CD"].iloc[-1]) if "CD" in df.columns else None,
    }

    summary_path = project_root / post_cfg.history_summary
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def plot_curves(history_path: Path, post_cfg: PostProcessConfig, project_root: Path) -> Dict[str, Path]:
    """绘制升力/阻力与残差的迭代曲线。"""

    df = pd.read_csv(history_path)
    output_paths = {}

    if {"ITER", "CL", "CD"}.issubset(df.columns):
        plt.figure(figsize=(8, 4))
        plt.plot(df["ITER"], df["CL"], label="CL")
        plt.plot(df["ITER"], df["CD"], label="CD")
        plt.xlabel("迭代步")
        plt.ylabel("系数")
        plt.title("升力/阻力系数收敛曲线")
        plt.grid(True)
        plt.legend()
        lift_drag_path = project_root / post_cfg.plots["lift_drag"]
        lift_drag_path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(lift_drag_path, dpi=200)
        output_paths["lift_drag"] = lift_drag_path
        plt.close()

    residual_cols = [col for col in df.columns if col.startswith("RESIDUAL")]
    if "ITER" in df.columns and residual_cols:
        plt.figure(figsize=(8, 4))
        for col in residual_cols:
            plt.semilogy(df["ITER"], df[col], label=col)
        plt.xlabel("迭代步")
        plt.ylabel("残差 (对数尺度)")
        plt.title("残差衰减曲线")
        plt.grid(True)
        plt.legend()
        residual_path = project_root / post_cfg.plots["residuals"]
        residual_path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(residual_path, dpi=200)
        output_paths["residuals"] = residual_path
        plt.close()

    return output_paths


def postprocess(config_path: Path = CONFIG_PATH) -> Dict[str, Path]:
    """后处理主入口，生成摘要与曲线图。"""

    post_cfg, _, project_root, config = load_config(config_path)
    history_path = project_root / config["cfd"]["history_file"]
    if not history_path.exists():
        raise FileNotFoundError(f"找不到 SU2 历史文件: {history_path}")

    summary_path = summarize_history(history_path, post_cfg, project_root)
    plot_paths = plot_curves(history_path, post_cfg, project_root)
    plot_paths["summary"] = summary_path
    return plot_paths


if __name__ == "__main__":
    outputs = postprocess()
    for name, path in outputs.items():
        print(f"{name}: {path}")
