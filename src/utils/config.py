"""配置文件加载与路径管理工具。

该模块提供统一的配置加载、路径解析及目录创建能力，方便各环节脚本共享配置。所有注释均为中文，以便团队成员快速理解。
"""

from __future__ import annotations

import typing as t
from pathlib import Path

import yaml


class ConfigError(RuntimeError):
    """配置解析异常。"""


def load_config(config_path: t.Union[str, Path]) -> t.Tuple[dict, Path]:
    """读取 YAML 配置文件并返回配置字典及配置文件所在目录。

    参数:
        config_path: 配置文件路径，可以是相对路径或绝对路径。

    返回:
        (config, base_dir)
        config: 解析后的配置字典，内部并未做路径展开。
        base_dir: 配置文件所在目录，供后续路径解析使用。

    异常:
        ConfigError: 当文件不存在或解析失败时抛出。
    """

    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigError(f"配置文件不存在: {path}")

    try:
        with path.open("r", encoding="utf-8") as fh:
            config: dict = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - YAML 库自身的异常难以稳定复现
        raise ConfigError(f"配置文件解析失败: {exc}") from exc

    return config, path.parent


def resolve_path(base_dir: Path, target: t.Union[str, Path]) -> Path:
    """将配置中的路径字段统一转换为绝对路径。

    参数:
        base_dir: 配置文件所在目录。
        target: 配置项中的路径，可以为相对路径或绝对路径。

    返回:
        转换后的绝对路径。
    """

    path = Path(target)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    else:
        path = path.expanduser()
    return path


def ensure_directory(path: t.Union[str, Path]) -> Path:
    """确保目录存在，不存在则递归创建。

    参数:
        path: 目标目录路径。

    返回:
        目录对应的 :class:`Path` 对象。
    """

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_text_file(path: t.Union[str, Path], content: str, encoding: str = "utf-8") -> Path:
    """以 UTF-8 编码写出文本文件，常用于生成 SU2 配置等文本文件。

    参数:
        path: 输出文件路径。
        content: 写入的文本内容。
        encoding: 文本编码，默认 UTF-8。

    返回:
        文件对应的 :class:`Path` 对象。
    """

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding=encoding)
    return file_path
