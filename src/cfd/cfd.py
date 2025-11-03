"""SU2 气动计算配置生成与自动求解脚本。"""

from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path
from typing import Dict

from ..post.postprocess import run_postprocessing
from ..utils.config import ensure_directory, load_config, resolve_path, write_text_file

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)


def _format_bool(flag: bool) -> str:
    return "YES" if flag else "NO"


def _build_su2_config(config: Dict, mesh_path: Path) -> str:
    """根据配置组装 SU2 配置文件文本。"""

    cfd_cfg = config.get("cfd", {})
    fluid = cfd_cfg.get("fluid", {})
    flight = cfd_cfg.get("flight_condition", {})
    numerics = cfd_cfg.get("numerics", {})
    markers = cfd_cfg.get("markers", {})
    output = cfd_cfg.get("output", {})

    model_cfg = config.get("model", {})
    profile = model_cfg.get("profile", {})
    ref_length = float(profile.get("length", 1.0))

    gamma = float(fluid.get("gamma", 1.4))
    gas_constant = float(fluid.get("gas_constant", 287.05))
    temperature = float(fluid.get("temperature", 288.15))
    pressure = float(fluid.get("pressure", 101325.0))
    density = float(fluid.get("density", 1.225))
    viscosity = float(fluid.get("viscosity", 1.81e-5))

    velocity = float(flight.get("velocity", 15.0))
    aoa = float(flight.get("aoa", 0.0))
    sideslip = float(flight.get("sideslip", 0.0))

    speed_of_sound = math.sqrt(max(gamma * gas_constant * temperature, 1e-8))
    mach_number = velocity / speed_of_sound
    reynolds = density * velocity * ref_length / max(viscosity, 1e-12)

    solver = numerics.get("solver", "RANS")
    turbulence_model = numerics.get("turbulence_model", "SA")
    max_iterations = int(numerics.get("max_iterations", 500))
    cfl = float(numerics.get("cfl", 5.0))
    cfl_adapt = bool(numerics.get("cfl_adapt", True))
    cfl_param = numerics.get("cfl_adapt_param", [0.5, 5.0, 1.1])
    linear_solver = numerics.get("linear_solver", "FGMRES")
    linear_solver_prec = numerics.get("linear_solver_prec", "ILU")

    wall_marker = markers.get("wall", "FUSELAGE")
    farfield_marker = markers.get("farfield", "FARFIELD")
    symmetry_marker = markers.get("symmetry", [])
    monitoring_marker = markers.get("monitoring", wall_marker)

    history_file = output.get("history", "history.csv")
    surface_file = output.get("surface", "surface_flow.dat")
    volume_file = output.get("volume", "flow.vtu")
    restart_file = output.get("restart", "restart_flow.dat")
    forces_file = output.get("forces_breakdown", "forces_breakdown.dat")

    symmetry_str = ""
    if symmetry_marker:
        if isinstance(symmetry_marker, str):
            symmetry_marker = [symmetry_marker]
        symmetry_str = "\nMARKER_SYM = ( " + ", ".join(symmetry_marker) + " )"

    lines = [
        "%------------------------- 基本设置 ---------------------------%",
        f"SOLVER= {solver}",
        f"MACH_NUMBER= {mach_number:.6f}",
        f"AOA= {aoa}",
        f"SIDESLIP_ANGLE= {sideslip}",
        f"FREESTREAM_PRESSURE= {pressure}",
        f"FREESTREAM_TEMPERATURE= {temperature}",
        f"FREESTREAM_DENSITY= {density}",
        f"GAS_CONSTANT= {gas_constant}",
        f"GAMMA_VALUE= {gamma}",
        f"FREESTREAM_VISCOSITY= {viscosity}",
        f"FREESTREAM_VELOCITY= {velocity}",
        f"REYNOLDS_NUMBER= {reynolds:.2f}",
        f"REYNOLDS_LENGTH= {ref_length}",
        "",
        "%------------------------- 数值格式 ---------------------------%",
        f"NUM_METHOD_GRAD= GREEN_GAUSS",
        f"CFL_NUMBER= {cfl}",
        f"CFL_ADAPT= {_format_bool(cfl_adapt)}",
        f"CFL_ADAPT_PARAM= ( {', '.join(str(p) for p in cfl_param)} )",
        f"LINEAR_SOLVER= {linear_solver}",
        f"LINEAR_SOLVER_PREC= {linear_solver_prec}",
        f"LINEAR_SOLVER_ERROR= 1E-6",
        f"LINEAR_SOLVER_ITER= 5",
        f"MAX_ITER= {max_iterations}",
        "",
        "%------------------------- 网格及边界 ------------------------- %",
        f"MESH_FILENAME= {mesh_path.as_posix()}",
        f"MARKER_MONITORING= ( {monitoring_marker} )",
        f"MARKER_PLOTTING= ( {wall_marker} )",
        f"MARKER_CL= ( {wall_marker}, 0.0, 0.0, 0.0 )",
        f"MARKER_CD= ( {wall_marker}, 1.0, 0.0, 0.0 )",
        f"MARKER_FAR= ( {farfield_marker}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 )",
        f"MARKER_TURBULENT= ( {wall_marker}, {turbulence_model} )",
        f"MARKER_INLET= ( )",
        f"MARKER_OUTLET= ( )",
        symmetry_str,
        "",
        "%------------------------- 输出控制 ---------------------------%",
        f"SCREEN_OUTPUT= YES",
        f"OUTPUT_WRT_FREQ= 25",
        f"HISTORY_OUTPUT= {history_file}",
        f"SURFACE_FILENAME= {surface_file}",
        f"VOLUME_FILENAME= {volume_file}",
        f"RESTART_FILENAME= {restart_file}",
        f"WRT_FORCES_BREAKDOWN= YES",
        f"BREAKDOWN_FILENAME= {forces_file}",
    ]

    if solver.upper() == "RANS":
        lines.extend(
            [
                "",
                "%---------------------- 湍流模型参数 ----------------------%",
                f"TURBULENCE_MODEL= {turbulence_model}",
            ]
        )

    return "\n".join(line for line in lines if line)


def run_cfd(config_path: Path) -> Dict[str, Path]:
    """执行 SU2 求解流程。

    返回包含生成的配置文件路径，便于后续记录或调试。
    """

    config, base_dir = load_config(config_path)
    paths_cfg = config.get("paths", {})
    cfd_cfg = config.get("cfd", {})
    execution_cfg = config.get("execution", {})

    mesh_dir = resolve_path(base_dir, paths_cfg.get("mesh_output", "mesh"))
    cfd_dir = ensure_directory(resolve_path(base_dir, paths_cfg.get("cfd_output", "cfd")))

    mesh_path = mesh_dir / cfd_cfg.get("mesh_filename", "mesh.su2")
    if not mesh_path.is_file():
        raise FileNotFoundError(f"未找到 SU2 网格文件: {mesh_path}")

    config_path_out = cfd_dir / cfd_cfg.get("config_filename", "case.cfg")
    su2_config_text = _build_su2_config(config, mesh_path)
    write_text_file(config_path_out, su2_config_text)

    LOGGER.info("SU2 配置文件已生成: %s", config_path_out)

    if execution_cfg.get("run_solver", False):
        su2_exec = cfd_cfg.get("su2_executable")
        if not su2_exec:
            raise RuntimeError("未在配置中指定 su2_executable。")

        LOGGER.info("启动 SU2 CFD 计算 ...")
        try:
            subprocess.run([su2_exec, str(config_path_out)], cwd=cfd_dir, check=True)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"无法找到 SU2 可执行文件: {su2_exec}") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"SU2 求解失败，返回码 {exc.returncode}") from exc

        LOGGER.info("SU2 计算完成。")

        if execution_cfg.get("run_post", False):
            LOGGER.info("开始后处理 ...")
            run_postprocessing(config, cfd_dir)
    else:
        LOGGER.info("已跳过 SU2 求解 (execution.run_solver = false)。")

    return {"config": config_path_out}


def main() -> None:
    default_config = Path(__file__).resolve().parents[1] / "config.yaml"
    run_cfd(default_config)


if __name__ == "__main__":  # pragma: no cover
    main()
