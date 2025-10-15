"""使用 Matplotlib 跟踪优化进度的辅助模块。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")  # 确保在无图形界面的环境中也能绘图
import matplotlib.pyplot as plt

LOGGER = logging.getLogger(__name__)


@dataclass
class VisualizerConfig:
    """控制可视化器行为的配置。"""

    enabled: bool
    output_dir: Path
    filename_pattern: str
    dpi: int


class OptimisationVisualizer:
    """在优化过程中生成 CL/CD 趋势图。"""

    def __init__(self, config: VisualizerConfig) -> None:
        self.config = config
        if self.config.enabled:
            self.config.output_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.debug("可视化器初始化完成，输出目录为 %s", self.config.output_dir)

    def update(self, generation: int, history: List[Dict[str, float]]) -> None:
        """根据历史记录绘制最新的优化曲线。"""

        if not self.config.enabled:
            return
        figure, axes = plt.subplots(1, 1, figsize=(8, 5))
        axes.set_title(f"优化进度 (迭代至第 {generation} 代)")
        axes.set_xlabel("代数")
        axes.set_ylabel("CL/CD")

        generations = sorted({entry["generation"] for entry in history})
        best_values = []
        for gen in generations:
            gen_entries = [entry for entry in history if entry["generation"] == gen]
            if not gen_entries:
                continue
            best_values.append(max(entry["cl_cd"] for entry in gen_entries))

        axes.plot(generations[: len(best_values)], best_values, marker="o", linestyle="-")
        axes.grid(True, linestyle="--", linewidth=0.5)

        filename = self.config.filename_pattern.format(generation=generation)
        output_path = self.config.output_dir / filename
        figure.tight_layout()
        figure.savefig(output_path, dpi=self.config.dpi)
        plt.close(figure)
        LOGGER.info("已保存优化曲线图: %s", output_path)


__all__ = ["VisualizerConfig", "OptimisationVisualizer"]

