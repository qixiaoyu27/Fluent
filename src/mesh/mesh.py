"""网格生成模块，借助 Gmsh Python API 将 CAD 模型转化为 CFD 网格。

主要流程：
1. 读取配置文件，确定几何文件、网格尺寸以及边界层参数；
2. 初始化 Gmsh 并导入 STEP/IGES 模型；
3. 自动施加全局和局部网格尺寸控制；
4. 生成三维体网格并导出为 SU2 可读的 ``.msh`` 文件；
5. 返回生成的网格路径，供后续 SU2 计算使用。

所有参数均由 ``config.yaml`` 驱动，确保流程可重复、可追溯。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import gmsh
import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@dataclass
class MeshConfig:
    """Gmsh 网格控制参数。"""

    gmsh_path: str
    mesh_size_min: float
    mesh_size_max: float
    growth_rate: float
    surface_mesh_size: float
    boundary_layer_thickness: float
    boundary_layer_layers: int
    mesh_dimension: int
    geometry_file: str
    output_mesh: str


def load_config(path: Path = CONFIG_PATH) -> Tuple[MeshConfig, Path]:
    """读取配置并返回 ``MeshConfig`` 和输出目录。"""

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    mesh_cfg = MeshConfig(**config["mesh"])
    project_root = Path(path).resolve().parents[1]
    output_path = project_root / mesh_cfg.output_mesh
    output_path.parent.mkdir(parents=True, exist_ok=True)

    return mesh_cfg, project_root


def generate_mesh(config_path: Path = CONFIG_PATH) -> Path:
    """根据 ``config.yaml`` 自动生成 CFD 网格。"""

    mesh_cfg, project_root = load_config(config_path)

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)

    geom_path = project_root / mesh_cfg.geometry_file
    if not geom_path.exists():
        raise FileNotFoundError(f"找不到几何文件: {geom_path}")

    model = gmsh.model
    model.add("nacelle")
    gmsh.merge(str(geom_path))

    # 应用全局网格尺寸
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mesh_cfg.mesh_size_min)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_cfg.mesh_size_max)

    # 通过字段控制来设置边界层
    boundary_layer = model.mesh.field.add("BoundaryLayer")
    model.mesh.field.setNumbers(boundary_layer, "FacesList", model.getEntities(2))
    model.mesh.field.setNumber(boundary_layer, "hwall_n", mesh_cfg.boundary_layer_thickness)
    model.mesh.field.setNumber(boundary_layer, "thickness", mesh_cfg.boundary_layer_thickness)
    model.mesh.field.setNumber(boundary_layer, "ratio", mesh_cfg.growth_rate)
    model.mesh.field.setNumber(boundary_layer, "NumberOfLayers", mesh_cfg.boundary_layer_layers)

    surface_field = model.mesh.field.add("Constant")
    model.mesh.field.setNumber(surface_field, "F", mesh_cfg.surface_mesh_size)
    model.mesh.field.setNumbers(surface_field, "FacesList", model.getEntities(2))

    min_field = model.mesh.field.add("Min")
    model.mesh.field.setNumbers(min_field, "FieldsList", [boundary_layer, surface_field])
    model.mesh.field.setAsBackgroundMesh(min_field)

    model.mesh.generate(mesh_cfg.mesh_dimension)

    output_path = project_root / mesh_cfg.output_mesh
    gmsh.write(str(output_path))

    gmsh.finalize()

    return output_path.resolve()


if __name__ == "__main__":
    path = generate_mesh()
    print(f"网格已导出: {path}")
