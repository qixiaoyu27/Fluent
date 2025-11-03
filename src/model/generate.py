"""模型生成模块，负责根据配置文件使用 cadquery 构建航模整流罩的实体模型。

本模块提供 ``build_nacelle_from_config`` 主函数，通过读取 ``config.yaml`` 中的参数，
自动完成以下任务：

1. 构建由机身、鼻锥以及尾翼组成的整流罩外形；
2. 自动生成内部空腔（壁厚可配置），以方便后续布置科研设备；
3. 将模型导出为 STEP/STL 等常见格式；
4. 将导出结果路径返回给调用方。

整套流程只依赖于配置文件，无需额外手动操作，方便批量参数化设计。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import cadquery as cq
import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@dataclass
class NacelleConfig:
    """整流罩几何参数数据类。"""

    fuselage_length: float
    fuselage_radius: float
    nose_length_ratio: float
    wall_thickness: float
    fin_span: float
    fin_chord: float
    fin_thickness: float
    fin_sweep_ratio: float
    export_format: str


def load_config(path: Path = CONFIG_PATH) -> Tuple[NacelleConfig, Path]:
    """读取 ``config.yaml`` 并解析出模型参数以及输出目录。

    参数
    ----
    path:
        配置文件路径，默认指向 ``src/config.yaml``。

    返回
    ----
    tuple[NacelleConfig, Path]
        模型参数对象和模型文件输出目录。
    """

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    model_cfg = NacelleConfig(**config["model"])
    project_root = Path(path).resolve().parents[1]
    output_dir = project_root / config["project"]["output_dirs"]["model"]
    output_dir.mkdir(parents=True, exist_ok=True)

    return model_cfg, output_dir


def _create_fuselage(cfg: NacelleConfig) -> cq.Workplane:
    """创建机身主体（圆柱+鼻锥+尾锥）实体。"""

    total_length = cfg.fuselage_length
    nose_length = total_length * cfg.nose_length_ratio
    cylinder_length = total_length - nose_length

    # 1. 创建圆柱机身
    fuselage = cq.Workplane("XY").circle(cfg.fuselage_radius).extrude(cylinder_length)

    # 2. 鼻锥使用二次曲线控制点，通过 loft 生成平滑过渡
    nose_profile = (
        cq.Workplane("YZ")
        .workplane(offset=0)
        .spline(
            [
                (0, 0),
                (-nose_length * 0.25, cfg.fuselage_radius * 0.95),
                (-nose_length * 0.6, cfg.fuselage_radius * 0.55),
                (-nose_length, 0),
            ]
        )
    )
    nose = (
        nose_profile
        .revolve(360, (0, 0, 0), (0, 1, 0))
        .translate((cylinder_length, 0, 0))
    )

    # 3. 尾锥采用轻微收缩的锥形，保证气动顺滑
    tail = (
        cq.Workplane("XY")
        .workplane(offset=total_length)
        .circle(cfg.fuselage_radius * 0.9)
        .workplane(offset=total_length * 0.1)
        .circle(cfg.fuselage_radius * 0.2)
        .loft(combine=True, ruled=False)
    )

    return fuselage.union(nose).union(tail)


def _create_hollow(inner_body: cq.Workplane, cfg: NacelleConfig) -> cq.Workplane:
    """根据壁厚挖空机身，形成内部腔体。"""

    inner_radius = cfg.fuselage_radius - cfg.wall_thickness
    if inner_radius <= 0:
        raise ValueError("壁厚过大导致内部半径非正，请调整配置参数。")

    hollow_body = (
        cq.Workplane("XY")
        .circle(inner_radius)
        .extrude(cfg.fuselage_length * 0.95)
        .translate((cfg.fuselage_length * 0.025, 0, 0))
    )

    return inner_body.cut(hollow_body)


def _create_fins(cfg: NacelleConfig) -> cq.Workplane:
    """创建四片对称的尾翼，用于提高稳定性。"""

    base_points = [
        (0, 0),
        (cfg.fin_chord, cfg.fin_thickness / 2),
        (cfg.fin_chord * (1 - cfg.fin_sweep_ratio), cfg.fin_thickness / 2),
        (0, -cfg.fin_thickness / 2),
    ]
    fin_profile = (
        cq.Workplane("XZ")
        .workplane(offset=cfg.fuselage_length * 0.85)
        .center(0, cfg.fuselage_radius)
        .polyline(base_points)
        .close()
        .extrude(cfg.fin_span)
    )

    fin_solid = fin_profile.translate((0, 0, -cfg.fin_span / 2))

    fins = fin_solid
    for angle in (90, 180, 270):
        fins = fins.union(fin_solid.rotate((0, 0, 0), (1, 0, 0), angle))

    return fins


def build_nacelle_from_config(config_path: Path = CONFIG_PATH) -> Path:
    """高层接口：生成整流罩并导出模型文件。

    返回值为导出模型的绝对路径，后续模块可以直接引用。
    """

    cfg, output_dir = load_config(config_path)

    body = _create_fuselage(cfg)
    body = _create_hollow(body, cfg)
    fins = _create_fins(cfg)
    nacelle = body.union(fins)

    export_path = output_dir / f"nacelle.{cfg.export_format}"

    if cfg.export_format.lower() == "step":
        cq.exporters.export(nacelle, str(export_path), exportType="STEP")
    elif cfg.export_format.lower() == "stl":
        cq.exporters.export(nacelle, str(export_path), exportType="STL")
    else:
        raise ValueError(f"不支持的导出格式: {cfg.export_format}")

    return export_path.resolve()


if __name__ == "__main__":
    path = build_nacelle_from_config()
    print(f"模型已生成: {path}")
