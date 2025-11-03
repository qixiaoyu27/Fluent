"""使用 Gmsh 将整流罩 STEP 模型转化为 SU2 可用的体网格。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

try:
    import gmsh  # type: ignore
except ImportError as exc:  # pragma: no cover - 测试环境未必安装 Gmsh Python API
    raise SystemExit("未检测到 gmsh Python API，请先安装: pip install gmsh") from exc

from ..utils.config import ensure_directory, load_config, resolve_path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)


def _compute_bounding_box(volumes: Iterable[Tuple[int, int]]) -> Tuple[float, float, float, float, float, float]:
    """返回指定体实体的整体包围盒。"""

    bbox = [float("inf"), float("-inf"), float("inf"), float("-inf"), float("inf"), float("-inf")]
    for dim, tag in volumes:
        local = gmsh.model.getBoundingBox(dim, tag)
        bbox[0] = min(bbox[0], local[0])
        bbox[1] = max(bbox[1], local[1])
        bbox[2] = min(bbox[2], local[2])
        bbox[3] = max(bbox[3], local[3])
        bbox[4] = min(bbox[4], local[4])
        bbox[5] = max(bbox[5], local[5])
    return tuple(bbox)  # type: ignore[return-value]


def _classify_surfaces(
    surfaces: Iterable[Tuple[int, int]],
    object_bbox: Tuple[float, float, float, float, float, float],
) -> Tuple[List[int], List[int]]:
    """根据表面尺寸自动区分壁面与远场面。"""

    xmin, xmax, ymin, ymax, zmin, zmax = object_bbox
    object_size = max(xmax - xmin, ymax - ymin, zmax - zmin)
    threshold = object_size * 1.5

    wall_tags: List[int] = []
    farfield_tags: List[int] = []

    for dim, tag in surfaces:
        sxmin, sxmax, symin, symax, szmin, szmax = gmsh.model.getBoundingBox(dim, tag)
        surface_size = max(sxmax - sxmin, symax - symin, szmax - szmin)
        if surface_size <= threshold:
            wall_tags.append(tag)
        else:
            farfield_tags.append(tag)

    if not wall_tags:
        LOGGER.warning("未检测到壁面标签，默认将全部曲面设置为壁面。")
        wall_tags = [tag for _, tag in surfaces]
        farfield_tags = []

    if not farfield_tags:
        LOGGER.warning("未检测到远场标签，可能导致 SU2 边界条件缺失。")

    return wall_tags, farfield_tags


def generate_mesh(config_path: Path) -> Dict[str, Path]:
    """根据配置文件生成体网格，并导出 SU2 网格文件。"""

    config, base_dir = load_config(config_path)
    paths_cfg = config.get("paths", {})
    mesh_cfg = config.get("mesh", {})
    gmsh_cfg = mesh_cfg.get("gmsh", {})

    model_dir = resolve_path(base_dir, paths_cfg.get("model_output", "model"))
    mesh_dir = ensure_directory(resolve_path(base_dir, paths_cfg.get("mesh_output", "mesh")))

    step_path = model_dir / mesh_cfg.get("geometry_filename", "model.step")
    mesh_path = mesh_dir / mesh_cfg.get("mesh_filename", "mesh.su2")

    if not step_path.is_file():
        raise FileNotFoundError(f"未找到 STEP 模型文件: {step_path}")

    LOGGER.info("加载 STEP 几何: %s", step_path)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.merge(str(step_path))

        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(dim=3)
        if not volumes:
            raise RuntimeError("导入的 STEP 未包含体实体，请确认模型导出设置。")

        object_bbox = _compute_bounding_box(volumes)
        xmin, xmax, ymin, ymax, zmin, zmax = object_bbox
        center = ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)
        max_extent = max(xmax - xmin, ymax - ymin, zmax - zmin)

        farfield_scale = float(gmsh_cfg.get("farfield_scale", 8.0))
        farfield_radius = max_extent * farfield_scale

        LOGGER.info("创建远场包络 (半径 %.3f m)", farfield_radius)
        farfield_tag = gmsh.model.occ.addSphere(*center, farfield_radius)
        gmsh.model.occ.synchronize()

        LOGGER.info("执行布尔差集以生成流场区域 ...")
        fluid_entities, _ = gmsh.model.occ.cut(
            [(3, farfield_tag)],
            volumes,
            removeObject=True,
            removeTool=True,
        )
        gmsh.model.occ.synchronize()

        if not fluid_entities:
            raise RuntimeError("布尔运算失败，未生成流体域。")

        # 设置物理分组，用于 SU2 边界条件识别
        surfaces = gmsh.model.getEntities(dim=2)
        wall_tags, farfield_tags = _classify_surfaces(surfaces, object_bbox)

        wall_name = gmsh_cfg.get("boundary_tags", {}).get("wall", "WALL")
        farfield_name = gmsh_cfg.get("boundary_tags", {}).get("farfield", "FARFIELD")

        LOGGER.info("添加物理分组: %s (%d 个面)", wall_name, len(wall_tags))
        gmsh.model.addPhysicalGroup(2, wall_tags, tag=1)
        gmsh.model.setPhysicalName(2, 1, wall_name)

        if farfield_tags:
            LOGGER.info("添加物理分组: %s (%d 个面)", farfield_name, len(farfield_tags))
            gmsh.model.addPhysicalGroup(2, farfield_tags, tag=2)
            gmsh.model.setPhysicalName(2, 2, farfield_name)

        fluid_tags = [tag for _, tag in fluid_entities]
        gmsh.model.addPhysicalGroup(3, fluid_tags, tag=3)
        gmsh.model.setPhysicalName(3, 3, "FLUID")

        min_size = float(gmsh_cfg.get("min_size", 0.003))
        max_size = float(gmsh_cfg.get("max_size", 0.008))
        mesh_order = int(gmsh_cfg.get("mesh_order", 1))
        algorithm = int(gmsh_cfg.get("algorithm", 5))
        recombine = bool(gmsh_cfg.get("recombine", False))

        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", min_size)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", max_size)
        gmsh.option.setNumber("Mesh.ElementOrder", mesh_order)
        gmsh.option.setNumber("Mesh.Algorithm3D", algorithm)
        gmsh.option.setNumber("Mesh.RecombineAll", 1 if recombine else 0)

        LOGGER.info("生成三维网格 ...")
        gmsh.model.mesh.generate(3)

        LOGGER.info("导出 SU2 网格: %s", mesh_path)
        gmsh.write(str(mesh_path))
    finally:
        gmsh.finalize()
    return {"mesh": mesh_path}


def main() -> None:
    default_config = Path(__file__).resolve().parents[1] / "config.yaml"
    generate_mesh(default_config)


if __name__ == "__main__":  # pragma: no cover - 直接执行脚本
    main()
