"""无人机几何优化流程的程序入口。"""
from __future__ import annotations

import argparse
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import yaml

from .model_generator import GeometryConfig, VSPModelGenerator
from .optimizer import DesignVariable, GeneticOptimizer, OptimizerConfig
from .su2_interface import SU2Config, SU2Interface
from .visualizer import OptimisationVisualizer, VisualizerConfig


@dataclass
class ProjectConfig:
    """封装项目配置字典及原始文件路径。"""

    raw: Dict[str, object]
    params_path: Path


def load_config(path: Path) -> ProjectConfig:
    """读取 YAML 配置文件并封装为 ``ProjectConfig``。"""

    # 通过 ``yaml.safe_load`` 读取配置文件，确保不会执行任意代码
    data = yaml.safe_load(path.read_text())
    return ProjectConfig(raw=data, params_path=path)


def setup_logging() -> None:
    """配置日志格式，确保后续步骤都有可追踪的输出。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


def create_generator(config: ProjectConfig) -> VSPModelGenerator:
    """根据配置构造几何生成器。"""

    # 读取几何与路径相关的配置，方便集中管理
    geometry_cfg = config.raw["geometry"]
    paths_cfg = config.raw["paths"]
    geometry = GeometryConfig(
        output_dir=Path(paths_cfg["output_root"]) / "geometry",
        output_formats=geometry_cfg.get("output_formats", ["vsp3"]),
        reference_area=float(geometry_cfg.get("reference_area", 0.6)),
        reference_span=float(geometry_cfg.get("reference_span", 3.5)),
        export_mesh_farfield_factor=float(geometry_cfg.get("export_mesh", {}).get("farfield_factor", 12.0)),
        export_mesh_max_edge_length=float(geometry_cfg.get("export_mesh", {}).get("max_edge_length", 0.2)),
        openvsp_python_path=(
            Path(paths_cfg["openvsp_python"]) if paths_cfg.get("openvsp_python") else None
        ),
    )
    # 返回几何生成器实例，该实例负责实际调用 OpenVSP
    return VSPModelGenerator(geometry)


def create_solver(config: ProjectConfig) -> SU2Interface:
    """创建 SU2 求解器接口对象。"""

    # 由于求解器需要几何参考尺寸，因此同时读取几何配置
    su2_cfg = config.raw["su2"]
    paths_cfg = config.raw["paths"]
    geometry_cfg = config.raw["geometry"]

    solver_config = SU2Config(
        executable=Path(paths_cfg["su2_executable"]),
        template_config=Path(su2_cfg["template_config"]),
        working_directory=Path(su2_cfg["working_directory"]),
        history_file=su2_cfg.get("history_file", "history.csv"),
        result_file=su2_cfg.get("result_file", "forces_breakdown.dat"),
        timeout_seconds=su2_cfg.get("timeout_seconds"),
        extra_cli_arguments=su2_cfg.get("extra_cli_arguments", []),
    )
    solver = SU2Interface(solver_config)
    # 将参考面积、参考长度传递给求解器，以便在模板中自动替换
    solver.extra_parameters = {
        "reference_area": geometry_cfg.get("reference_area", 0.6),
        "reference_length": geometry_cfg.get("reference_span", 3.5) / 2.0,
    }
    return solver


def create_visualizer(config: ProjectConfig) -> OptimisationVisualizer:
    """构造优化过程可视化器。"""

    # 获取可视化配置，默认为启用状态且输出到 ``results/plots``
    viz_cfg = config.raw.get("visualization", {})
    visualizer_config = VisualizerConfig(
        enabled=viz_cfg.get("enabled", True),
        output_dir=Path(viz_cfg.get("output_dir", "results/plots")),
        filename_pattern=viz_cfg.get("filename_pattern", "generation_{generation:03d}.png"),
        dpi=viz_cfg.get("dpi", 150),
    )
    return OptimisationVisualizer(visualizer_config)


def create_optimizer(
    config: ProjectConfig,
    generator: VSPModelGenerator,
    solver: SU2Interface,
    visualizer: OptimisationVisualizer,
) -> GeneticOptimizer:
    """组合几何生成器、求解器与设计变量创建遗传算法优化器。"""

    opt_cfg = config.raw["optimizer"]
    variables = [
        DesignVariable(
            name=name,
            minimum=float(attrs["min"]),
            maximum=float(attrs["max"]),
            default=float(attrs.get("default", attrs["min"])),
        )
        for name, attrs in config.raw["design_variables"].items()
    ]
    optimizer_config = OptimizerConfig(
        population_size=int(opt_cfg["population_size"]),
        generations=int(opt_cfg["generations"]),
        crossover_rate=float(opt_cfg["crossover_rate"]),
        mutation_rate=float(opt_cfg["mutation_rate"]),
        mutation_sigma=float(opt_cfg["mutation_sigma"]),
        tournament_size=int(opt_cfg.get("tournament_size", 3)),
        elitism=int(opt_cfg.get("elitism", 1)),
        objective=opt_cfg.get("objective", "maximize_cl_cd"),
        target_cl=float(opt_cfg.get("target_cl", 0.7)),
        history_csv=Path(opt_cfg.get("history_csv", "results/optimization_history.csv")),
    )
    # 实例化遗传算法优化器，后续 ``main`` 会驱动其完成迭代
    return GeneticOptimizer(generator, solver, variables, optimizer_config, visualizer)


def main(params_path: Path) -> None:
    """主流程：加载配置、构建各组件并执行优化。"""

    setup_logging()
    config = load_config(params_path)

    project_cfg = config.raw["project"]
    random_seed = project_cfg.get("random_seed")
    if random_seed is not None:
        # 固定随机种子以便复现实验结果
        random.seed(random_seed)

    generator = create_generator(config)
    solver = create_solver(config)
    visualizer = create_visualizer(config)
    optimizer = create_optimizer(config, generator, solver, visualizer)

    # 运行优化算法，得到最优设计参数与气动系数
    best_design, best_coefficients = optimizer.optimise()

    # 将最终结果转为可序列化的字典，便于保存或输出
    summary = {
        "best_design": best_design,
        "coefficients": {
            "CL": best_coefficients.cl,
            "CD": best_coefficients.cd,
            "CL_CD": best_coefficients.cl_cd,
        },
    }

    if config.raw.get("postprocessing", {}).get("export_summary", True):
        summary_path = Path(config.raw.get("postprocessing", {}).get("summary_path", "results/best_design_summary.yaml"))
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(yaml.safe_dump(summary))
        logging.info("Saved optimisation summary to %s", summary_path)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行无人机气动设计优化流程")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/params.yaml"),
        help="指定 YAML 配置文件路径",
    )
    args = parser.parse_args()
    main(args.config)

