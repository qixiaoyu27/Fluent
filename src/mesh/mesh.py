"""利用 Gmsh 完成整流罩外流场的网格划分。

该模块读取 ``config.yaml`` 中的网格设置、几何路径等信息，导入 STEP 模型、
执行尺寸控制，并按照配置自动创建物理分组，最终导出 SU2 可读取的网格文件。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

import gmsh

from utils.config import load_config, resolve_path


@dataclass
class PhysicalGroup:
    """描述需要在网格中创建的物理分组。"""

    name: str
    dimension: int
    entity_tags: List[int]


def _select_by_box(entities: Iterable[int], bounds: List[float]) -> List[int]:
    """根据包围盒筛选满足范围条件的实体。"""
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    selected: List[int] = []
    for tag in entities:
        bxmin, bymin, bzmin, bxmax, bymax, bzmax = gmsh.model.getBoundingBox(2, tag)
        if (
            bxmin >= xmin - 1e-5
            and bxmax <= xmax + 1e-5
            and bymin >= ymin - 1e-5
            and bymax <= ymax + 1e-5
            and bzmin >= zmin - 1e-5
            and bzmax <= zmax + 1e-5
        ):
            selected.append(tag)
    return selected


def _build_physical_groups(mesh_cfg: Dict[str, dict]) -> List[PhysicalGroup]:
    """解析配置并构建物理分组对象。"""
    surfaces = [tag for _, tag in gmsh.model.getEntities(2)]
    groups: List[PhysicalGroup] = []
    name_to_tags: Dict[str, List[int]] = {}

    for boundary in mesh_cfg.get("boundary_groups", []):
        name = boundary["name"]
        selection = boundary.get("selection", {})
        group_tags: List[int]

        if selection.get("type") == "box":
            group_tags = _select_by_box(surfaces, selection["bounds"])
        elif selection.get("type") == "complement":
            reference_names = selection.get("reference", [])
            reference_tags: Set[int] = set()
            for ref in reference_names:
                reference_tags.update(name_to_tags.get(ref, []))
            group_tags = [tag for tag in surfaces if tag not in reference_tags]
        else:
            raise ValueError(f"未知的选择类型: {selection}")

        name_to_tags[name] = group_tags
        groups.append(PhysicalGroup(name=name, dimension=int(boundary["dimension"]), entity_tags=group_tags))

    fluid_cfg = mesh_cfg.get("fluid_volume")
    if fluid_cfg:
        volumes = [tag for _, tag in gmsh.model.getEntities(3)]
        if not volumes:
            raise RuntimeError("未找到三维体实体，无法创建流体域物理分组。")
        groups.append(PhysicalGroup(name=fluid_cfg["name"], dimension=int(fluid_cfg["dimension"]), entity_tags=volumes))

    return groups


def generate_mesh() -> Path:
    """执行网格划分并返回生成的 SU2 网格文件路径。"""
    config = load_config()
    mesh_cfg = config["mesh"]
    paths = config["paths"]

    model_path = resolve_path(paths["model_output"])
    mesh_output = resolve_path(paths["mesh_output"])
    vtk_output = resolve_path(paths["mesh_visualization"])

    mesh_output.parent.mkdir(parents=True, exist_ok=True)
    vtk_output.parent.mkdir(parents=True, exist_ok=True)

    gmsh.initialize()
    gmsh.model.add("nacelle")

    try:
        if not model_path.exists():
            raise FileNotFoundError(f"未找到几何文件: {model_path}")

        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", float(mesh_cfg["characteristic_length_min"]))
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", float(mesh_cfg["characteristic_length_max"]))
        gmsh.option.setNumber("Mesh.Algorithm3D", float(mesh_cfg.get("algorithm", 6)))

        gmsh.merge(str(model_path))
        # 对导入几何中的所有点应用全局尺寸控制，便于精细调节网格密度。
        gmsh.model.mesh.setSize(gmsh.model.getEntities(0), float(mesh_cfg["characteristic_length_max"]))
        gmsh.model.mesh.generate(3)

        groups = _build_physical_groups(mesh_cfg)
        for group in groups:
            if not group.entity_tags:
                print(f"警告: 物理分组 {group.name} 未选中任何实体。")
                continue
            tag = gmsh.model.addPhysicalGroup(group.dimension, group.entity_tags)
            gmsh.model.setPhysicalName(group.dimension, tag, group.name)

        gmsh.write(str(mesh_output))
        gmsh.write(str(vtk_output))
    finally:
        gmsh.finalize()

    return mesh_output


def main() -> None:
    """命令行入口，执行网格划分并提示输出路径。"""
    path = generate_mesh()
    print(f"网格已生成: {path}")


if __name__ == "__main__":
    main()
