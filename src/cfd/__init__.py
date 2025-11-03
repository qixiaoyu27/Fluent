"""CFD 求解子模块。"""

from .cfd import run, run_solver, write_su2_config, build_su2_config_text, PipelineConfig

__all__ = [
    "run",
    "run_solver",
    "write_su2_config",
    "build_su2_config_text",
    "PipelineConfig",
]
