"""气动仿真模块

该模块负责将网格与飞行条件写入 SU2 配置文件，调用 SU2_CFD 可执行程序进行仿真，
并在仿真完成后自动触发后处理流程。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

import yaml

from ..post import postprocess


@dataclass
class FlightCondition:
    """飞行条件参数集合。"""

    velocity: float
    altitude: float
    reference_length: float
    reference_area: float
    air_density: float
    dynamic_viscosity: float
    speed_of_sound: float
    sideslip_angle: float
    angle_of_attack: float

    @property
    def mach_number(self) -> float:
        """根据速度与声速估算马赫数。"""

        return self.velocity / self.speed_of_sound

    @property
    def reynolds_number(self) -> float:
        """根据速度、参考长度和动力粘度计算雷诺数。"""

        return self.air_density * self.velocity * self.reference_length / self.dynamic_viscosity


@dataclass
class CFDConfig:
    """SU2 求解器相关配置。"""

    su2_executable: Path
    config_output: Path
    mesh_input: Path
    iteration_limit: int
    convergence_tolerance: float
    turbulence_model: str
    history_output: Path
    surface_output: Path

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CFDConfig":
        return cls(
            su2_executable=Path(data["su2_executable"]),
            config_output=Path(data.get("config_output", "result/cfd/nacelle.cfg")),
            mesh_input=Path(data.get("mesh_input", "result/mesh/nacelle.su2")),
            iteration_limit=int(data.get("iteration_limit", 500)),
            convergence_tolerance=float(data.get("convergence_tolerance", 1e-5)),
            turbulence_model=str(data.get("turbulence_model", "SA")),
            history_output=Path(data.get("history_output", "result/cfd/history.csv")),
            surface_output=Path(data.get("surface_output", "result/cfd/surface_flow.csv")),
        )


@dataclass
class PipelineConfig:
    """聚合后的整体配置。"""

    cfd: CFDConfig
    flight: FlightCondition
    post: postprocess.PostConfig

    @classmethod
    def load(cls, config_path: Path) -> "PipelineConfig":
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(
            cfd=CFDConfig.from_dict(data["cfd"]),
            flight=FlightCondition(
                velocity=float(data["flight_condition"]["velocity"]),
                altitude=float(data["flight_condition"]["altitude"]),
                reference_length=float(data["flight_condition"]["reference_length"]),
                reference_area=float(data["flight_condition"]["reference_area"]),
                air_density=float(data["flight_condition"]["air_density"]),
                dynamic_viscosity=float(data["flight_condition"]["dynamic_viscosity"]),
                speed_of_sound=float(data["flight_condition"]["speed_of_sound"]),
                sideslip_angle=float(data["flight_condition"]["sideslip_angle"]),
                angle_of_attack=float(data["flight_condition"]["angle_of_attack"]),
            ),
            post=postprocess.PostConfig.from_dict(data["postprocess"]),
        )


def build_su2_config_text(cfg: PipelineConfig) -> str:
    """按照 SU2 语法生成配置文件内容。"""

    flight = cfg.flight
    cfd = cfg.cfd

    template = f"""
% ------------------------ 通用设置 ------------------------
MESH_FILENAME= {cfd.mesh_input.as_posix()}
SOLVER= RANS
MATH_PROBLEM= DIRECT
REGIME_TYPE= COMPRESSIBLE
REF_LENGTH= {flight.reference_length:.6f}
REF_AREA= {flight.reference_area:.6f}

% ----------------------- 物理参数 -----------------------
FREESTREAM_VELOCITY= {flight.velocity:.6f}
FREESTREAM_MACH_NUMBER= {flight.mach_number:.6f}
FREESTREAM_DENSITY= {flight.air_density:.6f}
FREESTREAM_TEMPERATURE= 288.150000
FREESTREAM_PRESSURE= 101325.000000
REYNOLDS_NUMBER= {flight.reynolds_number:.2f}
REYNOLDS_LENGTH= {flight.reference_length:.6f}
AOA= {flight.angle_of_attack:.6f}
SIDESLIP_ANGLE= {flight.sideslip_angle:.6f}

% ----------------------- 数值参数 -----------------------
CFL_NUMBER= 5.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.1, 1.5, 0.5, 20.0 )
ITER= {cfd.iteration_limit}
CONV_FILENAME= {cfd.history_output.as_posix()}
SCREEN_OUTPUT= YES

% ----------------------- 湍流模型 -----------------------
KIND_TURB_MODEL= {cfd.turbulence_model}

% ----------------------- 输出控制 -----------------------
OUTPUT_FILES= CSV
WRT_SOL_FREQ= 50
WRT_CON_FREQ= 1
SURFACE_FILENAME= {cfd.surface_output.as_posix()}
HISTORY_OUTPUT= {cfd.history_output.as_posix()}
"""

    return "\n".join(line.rstrip() for line in template.strip().splitlines()) + "\n"


def write_su2_config(cfg: PipelineConfig) -> Path:
    """写出 SU2 配置文件，并创建所需目录。"""

    cfd_cfg = cfg.cfd
    cfd_cfg.config_output.parent.mkdir(parents=True, exist_ok=True)

    config_text = build_su2_config_text(cfg)
    cfd_cfg.config_output.write_text(config_text, encoding="utf-8")
    return cfd_cfg.config_output


def run_solver(cfg: PipelineConfig, *, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """调用 SU2_CFD 求解器执行仿真。"""

    executable = cfg.cfd.su2_executable
    if not executable.exists():
        raise FileNotFoundError(f"未找到 SU2 可执行文件: {executable}")

    config_file = write_su2_config(cfg)

    command = [str(executable), str(config_file)]
    process = subprocess.run(
        command,
        cwd=cfg.cfd.config_output.parent,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # 保存运行日志，便于排查问题
    log_file = cfg.cfd.config_output.with_suffix(".log")
    log_file.write_text(process.stdout + "\n" + process.stderr, encoding="utf-8")

    if process.returncode != 0:
        raise RuntimeError(
            "SU2 求解失败，请检查日志文件了解更多细节。"
        )

    return process


def run(config_path: str | Path = "src/config.yaml", *, timeout: Optional[int] = None) -> Dict[str, Any]:
    """入口函数：写配置、运行求解器并执行后处理。"""

    cfg = PipelineConfig.load(Path(config_path))
    run_solver(cfg, timeout=timeout)
    return postprocess.run(cfg.post, cfg.cfd)


if __name__ == "__main__":  # pragma: no cover
    run()
