"""气动求解模块，负责调用 SU2 完成 CFD 计算并收集结果。

实现要点：
1. 读取 ``config.yaml``，将模板配置 ``lib/su2_template.cfg`` 渲染成最终的运行配置；
2. 自动更新网格、结果文件路径及工况参数；
3. 通过 ``subprocess`` 调用 SU2 可执行程序，实时输出控制台信息；
4. 解析 SU2 生成的历史文件（CSV），以便后处理阶段使用。

SU2 的安装路径可在 ``config.yaml`` 中自由配置，本模块只负责调度。
"""
from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@dataclass
class CFDConfig:
    """SU2 求解所需关键参数。"""

    su2_exec: str
    su2_config_template: str
    working_cfg: str
    history_file: str
    restart_file: str
    mach_number: float
    angle_of_attack: float
    reynolds_number: float
    reference_length: float
    reference_area: float


def load_config(path: Path = CONFIG_PATH) -> Tuple[CFDConfig, Dict[str, str], Path]:
    """读取配置，返回 CFD 参数、项目路径信息。"""

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    cfd_cfg = CFDConfig(**config["cfd"])
    project_root = Path(path).resolve().parents[1]
    output_dirs = {
        key: project_root / value for key, value in config["project"]["output_dirs"].items()
    }
    for dir_path in output_dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    return cfd_cfg, output_dirs, project_root, config


def _render_su2_cfg(
    cfd_cfg: CFDConfig,
    output_dirs: Dict[str, Path],
    project_root: Path,
    full_config: Dict,
) -> Path:
    """根据模板渲染 SU2 配置文件。"""

    template_path = project_root / cfd_cfg.su2_config_template
    if not template_path.exists():
        raise FileNotFoundError(f"未找到 SU2 配置模板: {template_path}")

    mesh_file = project_root / full_config["mesh"]["output_mesh"]

    with template_path.open("r", encoding="utf-8") as f:
        content = f.read().format(
            mach_number=cfd_cfg.mach_number,
            angle_of_attack=cfd_cfg.angle_of_attack,
            reynolds_number=cfd_cfg.reynolds_number,
            reference_area=cfd_cfg.reference_area,
            reference_length=cfd_cfg.reference_length,
            mesh_file=mesh_file,
            solution_file=output_dirs["cfd"] / "solution.dat",
            history_file=project_root / cfd_cfg.history_file,
            restart_file=project_root / cfd_cfg.restart_file,
            volume_file=output_dirs["cfd"] / "volume.dat",
            surface_file=output_dirs["cfd"] / "surface.dat",
        )

    working_cfg_path = project_root / cfd_cfg.working_cfg
    working_cfg_path.parent.mkdir(parents=True, exist_ok=True)
    working_cfg_path.write_text(content, encoding="utf-8")

    return working_cfg_path


def run_su2_solver(config_path: Path = CONFIG_PATH) -> Path:
    """调用 SU2 求解器执行 CFD 计算，并返回历史文件路径。"""

    cfd_cfg, output_dirs, project_root, full_config = load_config(config_path)
    working_cfg = _render_su2_cfg(cfd_cfg, output_dirs, project_root, full_config)

    exec_path = Path(cfd_cfg.su2_exec)
    if not exec_path.exists():
        raise FileNotFoundError(f"找不到 SU2 可执行文件: {exec_path}")

    cmd = [str(exec_path), str(working_cfg)]
    process = subprocess.Popen(cmd, cwd=project_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # 实时打印 SU2 输出，方便用户监控收敛情况
    for line in iter(process.stdout.readline, b""):
        if not line:
            break
        print(line.decode("utf-8", "ignore"), end="")

    process.wait()
    if process.returncode != 0:
        raise RuntimeError("SU2 求解失败，请检查配置或网格质量。")

    history_path = project_root / cfd_cfg.history_file
    if not history_path.exists():
        raise FileNotFoundError("SU2 未生成历史文件，无法继续后处理。")

    return history_path


def parse_history_to_json(history_path: Path, output_path: Path) -> Path:
    """解析 SU2 历史 CSV，提取升力、阻力与残差等关键数据。"""

    with history_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        history_data = list(reader)

    summary = {
        "iterations": len(history_data),
        "last_entry": history_data[-1] if history_data else {},
    }

    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    history = run_su2_solver()
    summary_path = Path(CONFIG_PATH).resolve().parents[1] / "result/cfd/history_summary.json"
    parse_history_to_json(history, summary_path)
    print(f"SU2 历史摘要已保存至: {summary_path}")
