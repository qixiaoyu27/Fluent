"""模型生成模块

该模块使用 CadQuery 根据配置文件中的参数自动生成航模整流罩的三维几何。
整流罩主要用于科研级的低速飞行任务（约 15 m/s），
代码会根据给定的长度、半径和壁厚构建旋转体，并导出 STEP/STL 文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import yaml

try:
    import cadquery as cq
except ImportError as exc:  # pragma: no cover - CadQuery 在 CI 中可能不可用
    raise RuntimeError(
        "CadQuery 未安装，请先在当前 Python 环境中安装 cadquery 包。"
    ) from exc


@dataclass
class ModelConfig:
    """从配置文件提取的整流罩建模参数。"""

    length: float
    max_radius: float
    wall_thickness: float
    export_step: bool
    export_stl: bool
    output_step: Path
    output_stl: Path

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelConfig":
        """根据字典数据构造配置对象。"""

        return cls(
            length=float(data["length"]),
            max_radius=float(data["max_radius"]),
            wall_thickness=float(data["wall_thickness"]),
            export_step=bool(data.get("export_step", True)),
            export_stl=bool(data.get("export_stl", False)),
            output_step=Path(data.get("output_step", "result/model/nacelle.step")),
            output_stl=Path(data.get("output_stl", "result/model/nacelle.stl")),
        )


def load_config(config_path: Path) -> ModelConfig:
    """读取 YAML 配置文件并返回建模配置。"""

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ModelConfig.from_dict(data["model"])


def build_streamlined_nacelle(cfg: ModelConfig) -> cq.Workplane:
    """根据配置构造整流罩三维几何模型。"""

    if cfg.wall_thickness >= cfg.max_radius:
        raise ValueError("壁厚必须小于最大半径，才能保证内部空腔存在。")

    # 通过控制点 spline 构造外轮廓线
    control_points = [
        (0.0, 0.0),
        (cfg.length * 0.12, cfg.max_radius * 0.55),
        (cfg.length * 0.35, cfg.max_radius * 0.9),
        (cfg.length * 0.65, cfg.max_radius),
        (cfg.length, cfg.max_radius * 0.98),
    ]

    outer_profile = (
        cq.Workplane("XZ")
        .moveTo(*control_points[0])
        .spline(control_points[1:], includeCurrent=False)
        .lineTo(cfg.length, -cfg.max_radius * 0.98)
        .spline(
            [
                (cfg.length * 0.65, -cfg.max_radius),
                (cfg.length * 0.35, -cfg.max_radius * 0.9),
                (cfg.length * 0.12, -cfg.max_radius * 0.55),
            ],
            includeCurrent=False,
        )
        .close()
    )

    outer_solid = outer_profile.revolve(
        angleDegrees=360,
        axisStart=(0, 0, 0),
        axisEnd=(0, 0, 1),
    )

    inner_radius = cfg.max_radius - cfg.wall_thickness
    inner_profile = (
        cq.Workplane("XZ")
        .moveTo(0.0, 0.0)
        .spline(
            [
                (cfg.length * 0.12, inner_radius * 0.55),
                (cfg.length * 0.35, inner_radius * 0.9),
                (cfg.length * 0.65, inner_radius),
                (cfg.length, inner_radius * 0.98),
            ],
            includeCurrent=False,
        )
        .lineTo(cfg.length, -inner_radius * 0.98)
        .spline(
            [
                (cfg.length * 0.65, -inner_radius),
                (cfg.length * 0.35, -inner_radius * 0.9),
                (cfg.length * 0.12, -inner_radius * 0.55),
            ],
            includeCurrent=False,
        )
        .close()
    )

    inner_solid = inner_profile.revolve(
        angleDegrees=360,
        axisStart=(0, 0, 0),
        axisEnd=(0, 0, 1),
    )

    nacelle = outer_solid.cut(inner_solid.translate((0, 0, cfg.wall_thickness * 0.5)))

    # 在尾部中心挖孔，用于与机身连接（简化处理）
    connector_radius = inner_radius * 0.4
    connector_length = cfg.length * 0.18
    nacelle = nacelle.cut(
        cq.Workplane("XY")
        .workplane(offset=cfg.length - connector_length)
        .circle(connector_radius)
        .extrude(connector_length + cfg.wall_thickness)
    )

    return nacelle


def export_geometry(model: cq.Workplane, cfg: ModelConfig) -> None:
    """将几何模型导出为 STEP/STL 文件。"""

    cfg.output_step.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_stl.parent.mkdir(parents=True, exist_ok=True)

    if cfg.export_step:
        cq.exporters.export(model, str(cfg.output_step))

    if cfg.export_stl:
        cq.exporters.export(model, str(cfg.output_stl))


def run(config_path: str | Path = "src/config.yaml") -> Path:
    """入口函数：加载配置、生成整流罩并导出模型。"""

    cfg = load_config(Path(config_path))
    nacelle = build_streamlined_nacelle(cfg)
    export_geometry(nacelle, cfg)
    return cfg.output_step


if __name__ == "__main__":  # pragma: no cover - 允许脚本独立运行
    run()
