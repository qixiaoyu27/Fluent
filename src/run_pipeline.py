"""整流罩设计全自动流水线

按顺序执行建模、网格划分、CFD 求解以及后处理，所有参数均来自 config.yaml。
"""

from __future__ import annotations

from pathlib import Path

from .model import generate
from .mesh import mesh
from .cfd import cfd


def run_all(config_path: str | Path = "src/config.yaml") -> None:
    """依次执行完整流程。"""

    config_path = Path(config_path)

    print("[1/3] 生成几何模型...")
    step_path = generate.run(config_path)
    print(f"    已导出 STEP: {step_path}")

    print("[2/3] 生成数值网格...")
    msh_path, su2_path = mesh.run(config_path)
    print(f"    网格文件: {msh_path}")
    print(f"    SU2 网格: {su2_path}")

    print("[3/3] 运行 SU2 仿真并后处理...")
    summary = cfd.run(config_path)
    print("    仿真完成，摘要指标如下：")
    for key, value in summary.items():
        print(f"        {key}: {value}")


if __name__ == "__main__":  # pragma: no cover
    run_all()
