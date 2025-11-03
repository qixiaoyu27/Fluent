"""整流罩 CFD 全流程自动化入口。"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .model.generate import generate_model
from .mesh.mesh import generate_mesh
from .cfd.cfd import run_cfd

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)


def run_pipeline(config_path: Path) -> None:
    """依次执行建模、网格与 CFD 计算。"""

    LOGGER.info("读取配置并执行建模阶段 ...")
    model_artifacts = generate_model(config_path)
    LOGGER.info("建模完成: %s", model_artifacts)

    LOGGER.info("进入网格划分阶段 ...")
    mesh_artifacts = generate_mesh(config_path)
    LOGGER.info("网格划分完成: %s", mesh_artifacts)

    LOGGER.info("启动 CFD 阶段 ...")
    cfd_artifacts = run_cfd(config_path)
    LOGGER.info("CFD 阶段完成: %s", cfd_artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="航模整流罩 CFD 全流程自动化工具")
    parser.add_argument(
        "config",
        nargs="?",
        default=Path(__file__).resolve().parent / "config.yaml",
        type=Path,
        help="配置文件路径 (默认: 项目 src/config.yaml)",
    )
    args = parser.parse_args()

    run_pipeline(args.config.resolve())


if __name__ == "__main__":  # pragma: no cover
    main()
