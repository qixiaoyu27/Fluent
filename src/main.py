"""一键运行航模整流罩气动分析流程的入口脚本。"""
from __future__ import annotations

from model.generate import generate_model
from mesh.mesh import generate_mesh
from cfd.cfd import run_cfd


def run_pipeline() -> None:
    """依次执行建模、网格划分、CFD 求解与后处理。"""
    model_path = generate_model()
    print(f"[1/3] 几何建模完成: {model_path}")

    mesh_path = generate_mesh()
    print(f"[2/3] 网格划分完成: {mesh_path}")

    results = run_cfd()
    for name, path in results.items():
        print(f"[3/3] {name}: {path}")


if __name__ == "__main__":
    run_pipeline()
