"""提供基于设计变量生成 OpenVSP 几何模型的工具。"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class GeometryConfig:
    """控制几何导出方式的配置参数。"""

    output_dir: Path
    output_formats: Iterable[str]
    reference_area: float
    reference_span: float
    export_mesh_farfield_factor: float
    export_mesh_max_edge_length: float
    openvsp_python_path: Optional[Path] = None


@dataclass
class ModelArtifacts:
    """描述单个几何导出结果的容器。"""

    design_id: str
    vsp_path: Path
    mesh_path: Optional[Path]
    stl_path: Optional[Path]
    metadata: Dict[str, float]


class VSPModelGenerator:
    """根据设计变量生成 OpenVSP 模型并可选地导出 STL 或 SU2 网格。"""

    PARAMETER_MAP = {
        "wing_span": ("Span", "XSec_1"),
        "wing_root_chord": ("Root_Chord", "XSec_1"),
        "wing_taper_ratio": ("Taper", "XSec_1"),
        "wing_dihedral": ("Dihedral", "XSec_1"),
        "wing_sweep": ("Sweep", "XSec_1"),
        "tail_volume_coefficient": ("TailVol", "Design"),
        "fuselage_length": ("Length", "Design"),
        "fuselage_diameter": ("Diameter", "Design"),
    }

    def __init__(self, config: GeometryConfig) -> None:
        self.config = config
        self.config.output_formats = tuple(config.output_formats)
        # 预加载 OpenVSP Python 接口，确保后续可以调用
        self._prepare_environment()
        # 保证几何文件输出目录存在
        self._ensure_output_dir()

    def _prepare_environment(self) -> None:
        """确保可以导入 OpenVSP Python 模块。"""

        if self.config.openvsp_python_path:
            import sys

            candidate = str(self.config.openvsp_python_path)
            if candidate not in sys.path:
                sys.path.append(candidate)
                LOGGER.debug("已将 OpenVSP Python 路径添加到 sys.path: %s", candidate)

        spec = importlib.util.find_spec("openvsp")
        if spec is None:
            raise RuntimeError(
                "无法找到 OpenVSP Python 模块，请确认 OpenVSP 已安装且 Python API 可用。"
            )
        self._vsp = importlib.import_module("openvsp")
        LOGGER.debug("OpenVSP Python 模块加载成功")

    def _ensure_output_dir(self) -> None:
        """创建导出目录，防止后续写文件失败。"""

        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.debug("确保几何输出目录存在: %s", self.config.output_dir)

    def generate_geometry(self, design_variables: Dict[str, float]) -> ModelArtifacts:
        """根据设计变量生成 VSP3 模型，并视配置导出 STL/SU2 文件。"""

        design_id = uuid.uuid4().hex[:8]
        LOGGER.info("开始生成设计 %s 的 OpenVSP 模型", design_id)
        vsp = self._vsp

        # 清空当前模型，保证生成过程从干净状态开始
        vsp.ClearVSPModel()

        wing_id = vsp.AddGeom("WING")
        vsp.SetGeomName(wing_id, f"MainWing_{design_id}")
        tail_id = vsp.AddGeom("WING")
        vsp.SetGeomName(tail_id, f"Tail_{design_id}")
        fuse_id = vsp.AddGeom("FUSELAGE")
        vsp.SetGeomName(fuse_id, f"Fuselage_{design_id}")

        for key, (parm, group) in self.PARAMETER_MAP.items():
            if key not in design_variables:
                continue
            value = float(design_variables[key])
            target_geom = wing_id
            if key.startswith("tail_"):
                target_geom = tail_id
            elif key.startswith("fuselage_"):
                target_geom = fuse_id

            try:
                vsp.SetParmVal(target_geom, parm, group, value)
            except Exception as exc:  # noqa: BLE001 - 保留异常类型以便补充上下文
                raise RuntimeError(
                    f"设置参数 {parm} (组 {group}) 对应 {key} 时失败"
                ) from exc

        # 分别针对主翼、尾翼、机身进行进一步的细化配置
        self._configure_tail(tail_id, design_variables)
        self._configure_fuselage(fuse_id, design_variables)
        self._configure_wing(wing_id, design_variables)

        # 所有参数更新完后刷新模型，确保内部状态一致
        vsp.Update()

        # 按需导出不同格式的几何/网格数据
        vsp_path = self._export_vsp(design_id)
        stl_path = self._export_stl(design_id) if "stl" in self.config.output_formats else None
        mesh_path = (
            self._export_su2(design_id)
            if "su2" in self.config.output_formats
            else None
        )

        LOGGER.info("完成设计 %s 的几何生成", design_id)
        return ModelArtifacts(
            design_id=design_id,
            vsp_path=vsp_path,
            mesh_path=mesh_path,
            stl_path=stl_path,
            metadata=self._derive_metadata(design_variables),
        )

    def _configure_wing(self, wing_id: str, design_variables: Dict[str, float]) -> None:
        """按照设计变量设置主翼的几何参数。"""

        vsp = self._vsp
        taper = float(design_variables.get("wing_taper_ratio", 0.45))
        root_chord = float(design_variables.get("wing_root_chord", 0.45))
        span = float(design_variables.get("wing_span", 3.0))
        tip_chord = root_chord * taper
        semi_span = span / 2.0

        vsp.SetParmVal(wing_id, "Root_Chord", "XSec_1", root_chord)
        vsp.SetParmVal(wing_id, "Tip_Chord", "XSec_1", tip_chord)
        vsp.SetParmVal(wing_id, "Span", "XSec_1", semi_span)
        vsp.SetParmVal(wing_id, "Sweep", "XSec_1", float(design_variables.get("wing_sweep", 4.0)))
        vsp.SetParmVal(wing_id, "Dihedral", "XSec_1", float(design_variables.get("wing_dihedral", 3.0)))
        LOGGER.debug(
            "主翼配置完成: 根弦长 %.3f, 梢弦长 %.3f, 翼展 %.3f",
            root_chord,
            tip_chord,
            span,
        )

    def _configure_tail(self, tail_id: str, design_variables: Dict[str, float]) -> None:
        """基于尾容积系数等参数构建水平尾翼。"""

        vsp = self._vsp
        tail_volume = float(design_variables.get("tail_volume_coefficient", 0.5))
        wing_area = float(self.config.reference_area)
        tail_area = tail_volume * wing_area
        tail_span = math.sqrt(tail_area * 4.0)

        vsp.SetParmVal(tail_id, "Root_Chord", "XSec_1", tail_span * 0.25)
        vsp.SetParmVal(tail_id, "Tip_Chord", "XSec_1", tail_span * 0.15)
        vsp.SetParmVal(tail_id, "Span", "XSec_1", tail_span / 2.0)
        vsp.SetParmVal(tail_id, "Sweep", "XSec_1", 20.0)
        vsp.SetParmVal(tail_id, "Dihedral", "XSec_1", 5.0)
        vsp.SetParmVal(tail_id, "X_Rel_Location", "XForm", float(design_variables.get("fuselage_length", 1.6)) * 0.9)
        LOGGER.debug("平尾配置完成，估算尾翼面积 %.3f", tail_area)

    def _configure_fuselage(self, fuse_id: str, design_variables: Dict[str, float]) -> None:
        """设置机身长度、直径等关键参数。"""

        vsp = self._vsp
        length = float(design_variables.get("fuselage_length", 1.6))
        diameter = float(design_variables.get("fuselage_diameter", 0.16))

        vsp.SetParmVal(fuse_id, "Length", "Design", length)
        vsp.SetParmVal(fuse_id, "Max_Diameter", "Design", diameter)
        vsp.SetParmVal(fuse_id, "Fine_Ratio", "Design", 12.0)
        vsp.SetParmVal(fuse_id, "X_Location", "XForm", length * 0.5)
        LOGGER.debug("机身配置完成，长度 %.3f、直径 %.3f", length, diameter)

    def _export_vsp(self, design_id: str) -> Path:
        """导出 VSP3 文件，作为几何的主表示。"""

        vsp = self._vsp
        file_path = self.config.output_dir / f"{design_id}.vsp3"
        vsp.WriteVSPFile(str(file_path), vsp.SET_ALL)
        LOGGER.info("已导出 VSP3 文件: %s", file_path)
        return file_path

    def _export_stl(self, design_id: str) -> Path:
        """调用 CFD 网格模块导出 STL 表面网格。"""

        vsp = self._vsp
        file_path = self.config.output_dir / f"{design_id}.stl"
        mesh_settings = vsp.CfdMeshSettingsMgr.GetSettingsPtr()
        mesh_settings.SetFARLevel(self.config.export_mesh_farfield_factor)
        mesh_settings.SetMaxEdgeLen(self.config.export_mesh_max_edge_length)
        vsp.SetComputationFileName(vsp.CFD_STL_TYPE, str(file_path))
        vsp.CfdMeshMgr.GenerateMesh()
        LOGGER.info("已导出 STL 网格: %s", file_path)
        return file_path

    def _export_su2(self, design_id: str) -> Path:
        """导出 SU2 可直接使用的网格文件。"""

        vsp = self._vsp
        file_path = self.config.output_dir / f"{design_id}.su2"
        mesh_settings = vsp.CfdMeshSettingsMgr.GetSettingsPtr()
        mesh_settings.SetFarMaxEdgeLen(self.config.export_mesh_max_edge_length)
        mesh_settings.SetFARLevel(self.config.export_mesh_farfield_factor)
        vsp.SetComputationFileName(vsp.CFD_SU2_TYPE, str(file_path))
        vsp.CfdMeshMgr.GenerateMesh()
        LOGGER.info("已导出 SU2 网格: %s", file_path)
        return file_path

    def _derive_metadata(self, design_variables: Dict[str, float]) -> Dict[str, float]:
        """根据设计变量推导额外的几何指标。"""

        metadata: Dict[str, float] = {}
        metadata.update(design_variables)
        metadata["aspect_ratio"] = (
            design_variables.get("wing_span", self.config.reference_span) ** 2
            / self.config.reference_area
        )
        metadata["wing_area"] = self.config.reference_area
        return metadata


__all__ = ["GeometryConfig", "ModelArtifacts", "VSPModelGenerator"]

