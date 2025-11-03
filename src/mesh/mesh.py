"""网格划分模块

使用 Gmsh 对 CadQuery 导出的 STEP 模型进行网格剖分，
支持对整体尺寸和边界层厚度进行配置，并在完成后输出 *.msh 与 *.su2 文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import yaml

try:
    import gmsh
except ImportError as exc:  # pragma: no cover - Gmsh 在 CI 中可能缺失
    raise RuntimeError("Gmsh Python API 未安装，请先安装 gmsh。") from exc


@dataclass
class MeshConfig:
    """网格生成相关配置。"""

    geometry_file: Path
    gmsh_geo_script: Path
    output_msh: Path
    output_su2: Path
    global_mesh_size: float
    boundary_layer_thickness: float
    boundary_layer_layers: int
    growth_rate: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MeshConfig":
        return cls(
            geometry_file=Path(data["geometry_file"]),
            gmsh_geo_script=Path(data.get("gmsh_geo_script", "result/mesh/nacelle.geo")),
            output_msh=Path(data.get("output_msh", "result/mesh/nacelle.msh")),
            output_su2=Path(data.get("output_su2", "result/mesh/nacelle.su2")),
            global_mesh_size=float(data.get("global_mesh_size", 0.01)),
            boundary_layer_thickness=float(data.get("boundary_layer_thickness", 0.0015)),
            boundary_layer_layers=int(data.get("boundary_layer_layers", 3)),
            growth_rate=float(data.get("growth_rate", 1.2)),
        )


def load_config(config_path: Path) -> MeshConfig:
    """读取 YAML 并构造网格配置。"""

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return MeshConfig.from_dict(data["mesh"])


def configure_boundary_layer(cfg: MeshConfig, surface_tags: list[int]) -> None:
    """通过场函数为指定曲面设置边界层。"""

    field_id = gmsh.model.mesh.field.add("BoundaryLayer")
    gmsh.model.mesh.field.setNumbers(field_id, "FacesList", surface_tags)
    gmsh.model.mesh.field.setNumber(field_id, "hfar", cfg.global_mesh_size)
    gmsh.model.mesh.field.setNumber(field_id, "hwall_n", cfg.boundary_layer_thickness / cfg.boundary_layer_layers)
    gmsh.model.mesh.field.setNumber(field_id, "thickness", cfg.boundary_layer_thickness)
    gmsh.model.mesh.field.setNumber(field_id, "ratio", cfg.growth_rate)
    gmsh.model.mesh.field.setAsBoundaryLayer(field_id)


def generate(cfg: MeshConfig) -> tuple[Path, Path]:
    """执行网格生成流程。"""

    if not cfg.geometry_file.exists():
        raise FileNotFoundError(f"未找到几何文件: {cfg.geometry_file}")

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("nacelle")

    gmsh.merge(str(cfg.geometry_file))

    # 简单地为所有几何面分配同样的网格尺寸
    gmsh.model.mesh.setSize(gmsh.model.getEntities(2), cfg.global_mesh_size)

    surface_tags = [surface[1] for surface in gmsh.model.getEntities(2)]
    if surface_tags:
        configure_boundary_layer(cfg, surface_tags)

    gmsh.model.mesh.generate(3)

    cfg.output_msh.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_su2.parent.mkdir(parents=True, exist_ok=True)

    gmsh.write(str(cfg.output_msh))
    gmsh.write(str(cfg.output_su2))

    # 导出 Geo 脚本，方便后续复现网格生成参数
    gmsh.write(str(cfg.gmsh_geo_script))

    gmsh.finalize()
    return cfg.output_msh, cfg.output_su2


def run(config_path: str | Path = "src/config.yaml") -> tuple[Path, Path]:
    """入口函数：读取配置并生成网格。"""

    cfg = load_config(Path(config_path))
    return generate(cfg)


if __name__ == "__main__":  # pragma: no cover
    run()
