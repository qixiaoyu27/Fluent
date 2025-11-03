"""基于 CadQuery 的整流罩参数化建模脚本。

核心步骤:
1. 解析配置文件中的几何参数，构建整流罩的轴线剖面曲线。
2. 使用 CadQuery 的旋转特征生成封闭的三维实体模型，并根据壁厚切除内部体积。
3. 将模型导出为 STEP (后续网格划分使用) 与 STL (快速预览使用)。

脚本既可以作为独立模块被调用，也可直接运行执行建模流程。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Tuple

try:
    import cadquery as cq
except ImportError as exc:  # pragma: no cover - CadQuery 在测试环境可能缺失
    raise SystemExit(
        "未检测到 cadquery，请先安装: pip install cadquery"
    ) from exc

from ..utils.config import ensure_directory, load_config, resolve_path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)


def _build_profile_points(params: Dict[str, float]) -> Tuple[Tuple[float, float], ...]:
    """根据配置组装用于旋转的轴对称剖面点集。

    为了获得平滑的整流罩外形，这里使用分段样条连接关键控制点。
    点集位于 XZ 平面，其中 X 轴为机体轴向，Z 轴为径向半径。
    """

    length = params["length"]
    inlet_radius = params["inlet_radius"]
    body_radius = params["body_radius"]
    tail_radius = params["tail_radius"]
    inlet_lip_length = params["inlet_lip_length"]
    tail_cone_length = params["tail_cone_length"]

    straight_length = length - inlet_lip_length - tail_cone_length
    if straight_length <= 0:
        raise ValueError("轴向长度不足，请检查 inlet_lip_length 与 tail_cone_length 配置。")

    # 使用控制点描述剖面曲线，后续将通过样条连接。
    return (
        (0.0, inlet_radius * 1.05),  # 轻微加大进气口，用于形成顺滑前缘
        (inlet_lip_length * 0.3, inlet_radius),
        (inlet_lip_length, body_radius),
        (inlet_lip_length + straight_length * 0.5, body_radius),
        (length - tail_cone_length * 0.8, body_radius * 0.9),
        (length - tail_cone_length * 0.2, tail_radius * 1.05),
        (length, tail_radius),
    )


def _create_solid(params: Dict[str, float]) -> cq.Workplane:
    """利用 CadQuery 旋转功能生成整流罩实体。"""

    wall_thickness = params["wall_thickness"]
    profile_points = _build_profile_points(params)

    # 创建外表面曲线
    outer_profile = cq.Workplane("XZ").spline(profile_points)
    outer_solid = outer_profile.revolve(360.0, (0, 0, 0), (1, 0, 0))

    if wall_thickness <= 0:
        raise ValueError("wall_thickness 必须为正值。")

    # 缩小剖面半径以生成内腔，实现实体减去内腔得到空心整流罩
    inner_points = tuple((x, max(r - wall_thickness, 0.0)) for x, r in profile_points)
    inner_profile = cq.Workplane("XZ").spline(inner_points)
    inner_solid = inner_profile.revolve(360.0, (0, 0, 0), (1, 0, 0))

    shell = outer_solid.cut(inner_solid)
    return shell


def generate_model(config_path: Path) -> Dict[str, Path]:
    """根据配置文件生成整流罩模型并输出 STEP/STL 文件。

    返回字典包含 STEP 与 STL 文件路径，供后续流程使用。
    """

    config, base_dir = load_config(config_path)
    paths_cfg = config.get("paths", {})
    model_cfg = config.get("model", {})

    model_dir = ensure_directory(resolve_path(base_dir, paths_cfg.get("model_output", "model")))
    step_path = model_dir / model_cfg.get("step_filename", "model.step")
    stl_path = model_dir / model_cfg.get("stl_filename", "model.stl")

    params = model_cfg.get("profile", {})
    wall_thickness = float(params.get("wall_thickness", 0.002))
    meshing_cfg = model_cfg.get("meshing", {})
    circle_segments = int(meshing_cfg.get("circle_segments", 120))
    angular_tolerance = 360.0 / max(circle_segments, 3)

    LOGGER.info("开始构建整流罩实体模型 ...")
    solid = _create_solid(params)

    LOGGER.info("导出 STEP 文件: %s", step_path)
    solid.val().exportStep(str(step_path))

    LOGGER.info("导出 STL 文件: %s", stl_path)
    cq.exporters.export(
        solid,
        str(stl_path),
        exportType="STL",
        tolerance=wall_thickness * 0.2,
        angularTolerance=angular_tolerance,
    )

    return {"step": step_path, "stl": stl_path}


def main() -> None:
    """命令行入口，默认读取项目内的 ``src/config.yaml``。"""

    default_config = Path(__file__).resolve().parents[1] / "config.yaml"
    generate_model(default_config)


if __name__ == "__main__":  # pragma: no cover - 直接运行脚本时执行
    main()
