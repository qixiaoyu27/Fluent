"""主流程脚本：串联几何建模、网格划分、CFD 求解与后处理。

用户只需执行 ``python -m src.pipeline`` 即可完成从 CAD 到 CFD 结果的全流程。
所有参数均通过 ``config.yaml`` 控制，便于统一管理与版本追踪。
"""
from __future__ import annotations

from pathlib import Path

from .cfd.cfd import run_su2_solver
from .mesh.mesh import generate_mesh
from .model.generate import build_nacelle_from_config
from .postprocess.analyze import postprocess

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def run_pipeline(config_path: Path = CONFIG_PATH) -> None:
    """执行完整流程，包括建模、网格、求解和后处理。"""

    print("[1/4] 正在生成 CAD 模型...")
    model_path = build_nacelle_from_config(config_path)
    print(f"模型文件输出：{model_path}")

    print("[2/4] 正在调用 Gmsh 生成网格...")
    mesh_path = generate_mesh(config_path)
    print(f"网格文件输出：{mesh_path}")

    print("[3/4] 正在运行 SU2 CFD 求解...")
    history_path = run_su2_solver(config_path)
    print(f"SU2 历史文件：{history_path}")

    print("[4/4] 正在执行后处理...")
    outputs = postprocess(config_path)
    for name, path in outputs.items():
        print(f"后处理输出 - {name}: {path}")


if __name__ == "__main__":
    run_pipeline()
