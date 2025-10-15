"""封装在 OpenVSP 生成的网格上运行 SU2 求解的工具。"""
from __future__ import annotations

import csv
import logging
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class SU2Config:
    """SU2 求解所需的路径、文件与运行参数。"""

    executable: Path
    template_config: Path
    working_directory: Path
    history_file: str
    result_file: str
    timeout_seconds: Optional[int]
    extra_cli_arguments: Iterable[str]


@dataclass
class AerodynamicCoefficients:
    """封装 SU2 输出的关键气动系数。"""

    cl: float
    cd: float
    cm: Optional[float]
    cl_cd: float
    metadata: Dict[str, float]


class SU2Interface:
    """协调 SU2 案例的准备、执行与结果解析。"""

    def __init__(self, config: SU2Config) -> None:
        self.config = config
        self.config.working_directory.mkdir(parents=True, exist_ok=True)
        self.extra_parameters: Dict[str, float] = {}
        LOGGER.debug("SU2 工作目录初始化完成: %s", self.config.working_directory)

    def evaluate_design(self, mesh_path: Path, parameters: Dict[str, float]) -> AerodynamicCoefficients:
        """对给定网格运行 SU2，并解析出气动系数。"""

        case_id = uuid.uuid4().hex[:8]
        case_dir = self.config.working_directory / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info("开始执行 SU2 案例 %s", case_id)

        # 将网格复制到案例目录，避免直接修改原始文件
        local_mesh = case_dir / mesh_path.name
        shutil.copy2(mesh_path, local_mesh)

        cfg_path = case_dir / "case.cfg"
        # 合并额外参数（例如参考面积）与设计变量，统一替换模板
        merged_parameters = {**self.extra_parameters, **parameters}
        cfg_path.write_text(self._render_template(local_mesh, merged_parameters))

        history_path = case_dir / self.config.history_file
        result_path = case_dir / self.config.result_file

        command = [str(self.config.executable), str(cfg_path)]
        command.extend(self.config.extra_cli_arguments)

        start_time = time.time()
        # 直接捕获标准输出，便于调试失败原因
        process = subprocess.Popen(
            command,
            cwd=case_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        stdout_lines: List[str] = []

        try:
            while True:
                line = process.stdout.readline()
                if line:
                    stdout_lines.append(line)
                    LOGGER.debug("SU2[%s] 输出: %s", case_id, line.strip())
                if process.poll() is not None and not line:
                    break
                if self.config.timeout_seconds and time.time() - start_time > self.config.timeout_seconds:
                    process.kill()
                    raise TimeoutError(f"案例 {case_id} 的 SU2 计算超时")
        finally:
            if process.stdout:
                process.stdout.close()

        if process.returncode != 0:
            raise RuntimeError(
                f"案例 {case_id} 的 SU2 求解失败，返回码 {process.returncode}.\n"
                + "".join(stdout_lines)
            )

        coefficients = self._parse_results(history_path, result_path)
        coefficients.metadata.update({"case_id": case_id})
        LOGGER.info(
            "SU2 案例 %s 完成 (CL=%.4f, CD=%.4f)",
            case_id,
            coefficients.cl,
            coefficients.cd,
        )
        return coefficients

    def _render_template(self, mesh_path: Path, parameters: Dict[str, float]) -> str:
        """将 SU2 模板配置中的占位符替换成实际参数。"""

        template = self.config.template_config.read_text()
        aoa = parameters.get("angle_of_attack")
        if aoa is None and "cruise_lift_coefficient" in parameters:
            cl_target = float(parameters["cruise_lift_coefficient"])
            cl0 = float(parameters.get("zero_lift_cl", 0.2))
            cl_alpha = float(parameters.get("cl_alpha_per_deg", 0.1))
            aoa = max(-2.0, min(12.0, (cl_target - cl0) / cl_alpha))
        if aoa is None:
            aoa = 3.0
        replacements = {
            "mesh_filename": mesh_path.name,
            "mach_number": parameters.get("cruise_mach_number", 0.08),
            "angle_of_attack": aoa,
            "reference_length": parameters.get("reference_length", 0.8),
            "reference_area": parameters.get("reference_area", 0.6),
        }
        rendered = template
        for key, value in replacements.items():
            rendered = rendered.replace(f"{{{key}}}", f"{value}")
        return rendered

    def _parse_results(self, history_path: Path, forces_path: Path) -> AerodynamicCoefficients:
        """读取 SU2 输出文件，提取气动系数。"""

        cl = None
        cd = None
        cm = None

        if history_path.exists():
            with history_path.open("r", newline="") as hist_file:
                reader = csv.DictReader(hist_file)
                for row in reader:
                    cl = float(row.get("CL", cl or 0.0))
                    cd = float(row.get("CD", cd or 0.0))
                    cm = float(row.get("CMz", cm or 0.0))
        else:
            LOGGER.warning("未找到历史文件 %s", history_path)

        if forces_path.exists():
            with forces_path.open("r", encoding="utf8", errors="ignore") as force_file:
                for line in force_file:
                    if line.strip().startswith("CL"):  # 例如: CL = 0.75
                        cl = float(line.split("=")[1])
                    if line.strip().startswith("CD"):
                        cd = float(line.split("=")[1])
                    if line.strip().startswith("CMz"):
                        cm = float(line.split("=")[1])
        else:
            LOGGER.warning("未找到力系数文件 %s", forces_path)

        if cl is None or cd is None:
            raise RuntimeError("无法从 SU2 输出中解析气动系数")

        return AerodynamicCoefficients(
            cl=cl,
            cd=cd,
            cm=cm,
            cl_cd=cl / cd if cd else float("inf"),
            metadata={},
        )


__all__ = ["SU2Config", "SU2Interface", "AerodynamicCoefficients"]

