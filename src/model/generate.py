"""利用 cadquery 构建航模整流罩的三维几何模型。

该脚本读取 ``config.yaml`` 中的建模参数，生成包含采样口的整流罩结构，
并导出为 STEP 文件供后续网格划分使用。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import cadquery as cq

from utils.config import load_config, resolve_path


def _build_profile(length: float, inlet_radius: float, outlet_radius: float) -> cq.Workplane:
    """创建用于旋转体的母线轮廓。

    这里选用 ``YZ`` 工作平面，并沿 ``X`` 轴进行旋转，从而生成轴对称的整流罩。
    为了获得平滑的过渡，使用 ``spline`` 定义外形变化。
    """
    control_points = [
        (0.0, inlet_radius),
        (length * 0.15, inlet_radius * 0.95),
        (length * 0.45, (inlet_radius + outlet_radius) * 0.55),
        (length * 0.75, outlet_radius * 1.05),
        (length, outlet_radius),
    ]

    profile = (
        cq.Workplane("YZ")
        .moveTo(*control_points[0])
        .spline(control_points[1:])
        .lineTo(length, 0.0)
        .lineTo(0.0, 0.0)
        .close()
    )
    return profile


def _add_sampling_ports(body: cq.Workplane, ports: Iterable[dict], wall_thickness: float) -> cq.Workplane:
    """根据配置中的参数向整流罩壁面添加采样口。

    采样口被建模为沿 ``Z`` 轴钻出的圆孔，位置以整流罩头部为参考。
    """
    for port in ports:
        position = float(port["position"])
        radius = float(port["radius"])
        cutter = (
            cq.Workplane("XY")
            .workplane(offset=position)
            .circle(radius)
            .extrude(2 * wall_thickness, both=True)
        )
        body = body.cut(cutter)
    return body


def generate_model() -> Path:
    """执行建模流程并返回生成的 STEP 文件路径。"""
    config = load_config()
    cad_cfg = config["cad"]

    length = float(cad_cfg["length"])
    inlet_radius = float(cad_cfg["inlet_radius"])
    outlet_radius = float(cad_cfg["outlet_radius"])
    wall_thickness = float(cad_cfg["wall_thickness"])

    profile = _build_profile(length, inlet_radius, outlet_radius)

    outer_solid = profile.revolve(360.0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    inner_profile = _build_profile(
        length,
        max(inlet_radius - wall_thickness, 1e-4),
        max(outlet_radius - wall_thickness, 1e-4),
    )
    inner_solid = inner_profile.revolve(360.0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    nacelle = outer_solid.cut(inner_solid)

    if cad_cfg.get("sampling_ports"):
        nacelle = _add_sampling_ports(nacelle, cad_cfg["sampling_ports"], wall_thickness)

    output_path = resolve_path(config["paths"]["model_output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cq.exporters.export(nacelle, str(output_path), tolerance=1e-4)

    return output_path


def main() -> None:
    """命令行入口，执行建模并提示输出文件位置。"""
    path = generate_model()
    print(f"模型已生成: {path}")


if __name__ == "__main__":
    main()
