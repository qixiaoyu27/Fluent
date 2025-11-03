"""配置加载工具。

该模块负责提供统一的配置读取与路径解析接口，确保所有模块共享相同的配置数据。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

# 仓库根目录: src/utils/config.py -> utils -> src -> 仓库
ROOT_DIR = Path(__file__).resolve().parents[2]
# 配置文件位于 src/config.yaml
CONFIG_PATH = ROOT_DIR / "src" / "config.yaml"


def load_config() -> Dict[str, Any]:
    """读取并返回完整的 YAML 配置。

    返回的数据结构会直接用于驱动建模、网格、计算等模块，因此在修改配置
    时只需更新 ``config.yaml`` 即可触发整个流程的变化。
    """
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_path(path_str: str) -> Path:
    """将配置文件中的相对路径转换为仓库根目录下的绝对路径。

    参数
    ----
    path_str:
        ``config.yaml`` 中定义的相对路径。

    返回
    ----
    Path
        转换后的绝对路径，父目录会在需要时由各模块自行创建。
    """
    return (ROOT_DIR / path_str).resolve()


__all__ = ["ROOT_DIR", "CONFIG_PATH", "load_config", "resolve_path"]
