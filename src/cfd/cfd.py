"""调用 SU2 完成气动求解并生成后处理结果。

本模块负责根据 ``config.yaml`` 生成 SU2 配置文件、执行计算以及读取历史
收敛数据进行可视化。除 SU2 外，不依赖额外的商业软件。
"""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt

from utils.config import load_config, resolve_path


def _format_marker(name: str, settings: Dict[str, float]) -> str:
    """将边界设置转换为 SU2 所需的 ``MARKER`` 字符串。"""
    marker_kind = settings.get("marker_kind", "WALL").upper()
    parameters = [name]
    for key, value in settings.items():
        if key == "marker_kind":
            continue
        parameters.append(f"{key.upper()}={value}")
    joined = ", ".join(parameters)
    return f"MARKER_{marker_kind}= ( {joined} )"


def _generate_su2_config(config: Dict[str, dict]) -> Path:
    """根据 YAML 配置生成 SU2 控制文件。"""
    paths = config["paths"]
    cfd_cfg = config["cfd"]

    mesh_path = resolve_path(paths["mesh_output"])
    workdir = resolve_path(paths["cfd_workdir"])
    workdir.mkdir(parents=True, exist_ok=True)

    su2_cfg_path = resolve_path(cfd_cfg["su2_config_output"])
    su2_cfg_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = [
        f"MESH_FILENAME= {mesh_path}",
        f"MESH_FORMAT= {cfd_cfg.get('mesh_format', 'SU2').upper()}",
        f"MACH_NUMBER= {cfd_cfg['reference']['mach_number']}",
        f"AOA= {cfd_cfg['reference']['aoa']}",
        f"REYNOLDS_NUMBER= {cfd_cfg['reference']['reynolds_number']}",
        f"REYNOLDS_LENGTH= {cfd_cfg['reference']['reference_length']}",
        f"FREESTREAM_TEMPERATURE= {cfd_cfg['freestream']['temperature']}",
        f"FREESTREAM_PRESSURE= {cfd_cfg['freestream']['pressure']}",
        f"FREESTREAM_DENSITY= {cfd_cfg['freestream']['density']}",
        f"KIND_TURB_MODEL= {cfd_cfg['solver_settings']['kind_turbulence_model']}",
        f"CFL_NUMBER= {cfd_cfg['solver_settings']['cfl_number']}",
        f"ITER= {cfd_cfg['solver_settings']['max_iterations']}",
        f"CONV_RESIDUAL_MINVAL= {cfd_cfg['solver_settings']['convergence_threshold']}",
        "RESTART_SOL= NO",
        "HISTORY_OUTPUT= YES",
        "VOLUME_FILENAME= flow.dat",
        "SURFACE_FILENAME= surface.dat",
    ]

    boundary_cfg = cfd_cfg.get("boundary_conditions", {})
    markers = [_format_marker(name, settings) for name, settings in boundary_cfg.items()]
    if markers:
        lines.extend(markers)
        marker_names = ", ".join(boundary_cfg.keys())
        lines.append(f"MARKER_PLOTTING= ( {marker_names} )")
        lines.append(f"MARKER_MONITORING= ( {marker_names} )")

    su2_cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return su2_cfg_path


def _run_solver(executable: Path, config_path: Path, workdir: Path) -> None:
    """调用 SU2 可执行文件完成求解。"""
    if not executable.exists():
        raise FileNotFoundError(f"未找到 SU2 可执行文件: {executable}")

    result = subprocess.run([str(executable), str(config_path)], cwd=workdir, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"SU2 计算失败: {result.stderr}")

    if result.stdout:
        print(result.stdout)


def _load_history(history_file: Path) -> Dict[str, List[float]]:
    """读取 SU2 ``history.csv`` 文件，返回列名到数据列表的映射。"""
    if not history_file.exists():
        raise FileNotFoundError(f"未找到历史文件: {history_file}")

    with history_file.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        data: Dict[str, List[float]] = {key: [] for key in reader.fieldnames or []}
        for row in reader:
            for key, value in row.items():
                try:
                    data[key].append(float(value))
                except (TypeError, ValueError):
                    pass
    return data


def _plot_history(data: Dict[str, List[float]], post_cfg: Dict[str, object]) -> Path:
    """根据配置绘制收敛历史图。"""
    output = resolve_path(post_cfg["plot_output"])
    output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8, 5))
    for column in post_cfg.get("plot_columns", []):
        x_col = column["x"]
        y_col = column["y"]
        if x_col not in data or y_col not in data:
            print(f"警告: 历史文件中缺少列 {x_col} 或 {y_col}，跳过绘图。")
            continue
        plt.plot(data[x_col], data[y_col], label=f"{column['category']}: {y_col}")

    plt.xlabel("迭代步")
    plt.ylabel("数值")
    plt.title("SU2 收敛历史")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output, dpi=200)
    plt.close()

    return output


def run_cfd() -> Dict[str, Path]:
    """执行 SU2 求解与后处理，返回关键结果文件路径。"""
    config = load_config()
    paths = config["paths"]
    cfd_cfg = config["cfd"]
    post_cfg = config["post_processing"]

    workdir = resolve_path(paths["cfd_workdir"])
    workdir.mkdir(parents=True, exist_ok=True)

    su2_config_path = _generate_su2_config(config)
    su2_executable = Path(cfd_cfg["su2_executable"])

    # 运行 SU2 求解器
    _run_solver(su2_executable, su2_config_path, workdir)

    history_file = resolve_path(post_cfg["history_file"])
    default_history = workdir / "history.csv"
    # 若用户未显式指定历史文件路径，则退回 SU2 的默认输出位置。
    if not history_file.exists() and default_history.exists():
        history_file = default_history
    data = _load_history(history_file)
    plot_path = _plot_history(data, post_cfg)

    return {"history": history_file, "plot": plot_path}


def main() -> None:
    """命令行入口，运行 CFD 求解并输出结果文件路径。"""
    results = run_cfd()
    for name, path in results.items():
        print(f"{name} => {path}")


if __name__ == "__main__":
    main()
