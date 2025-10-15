"""用于驱动 OpenVSP 与 SU2 联合优化的遗传算法实现。"""
from __future__ import annotations

import csv
import logging
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .model_generator import ModelArtifacts, VSPModelGenerator
from .su2_interface import AerodynamicCoefficients, SU2Interface
from .visualizer import OptimisationVisualizer

LOGGER = logging.getLogger(__name__)


@dataclass
class DesignVariable:
    """描述单个设计变量的取值范围及默认值。"""

    name: str
    minimum: float
    maximum: float
    default: float

    def sample(self) -> float:
        """在变量范围内随机采样，初始化种群时会调用。"""

        return random.uniform(self.minimum, self.maximum)

    def clamp(self, value: float) -> float:
        """将值限制在变量的合法范围内，防止突变后超界。"""

        return max(self.minimum, min(self.maximum, value))


@dataclass
class OptimizerConfig:
    """遗传算法的整体配置参数。"""

    population_size: int
    generations: int
    crossover_rate: float
    mutation_rate: float
    mutation_sigma: float
    tournament_size: int
    elitism: int
    objective: str
    target_cl: float
    history_csv: Path


class GeneticOptimizer:
    """使用简单遗传算法探索设计空间并寻找最优解。"""

    def __init__(
        self,
        generator: VSPModelGenerator,
        solver: SU2Interface,
        variables: Iterable[DesignVariable],
        config: OptimizerConfig,
        visualizer: Optional[OptimisationVisualizer] = None,
    ) -> None:
        self.generator = generator
        self.solver = solver
        self.variables = list(variables)
        self.config = config
        self.visualizer = visualizer
        # 保存每次评估的原始记录，既用于可视化也用于导出 CSV
        self._history: List[Dict[str, float]] = []
        self.config.history_csv.parent.mkdir(parents=True, exist_ok=True)

    def optimise(self) -> Tuple[Dict[str, float], AerodynamicCoefficients]:
        """执行遗传算法迭代并返回最优设计及其气动系数。"""

        # 初始化种群并计算适应度
        population = [self._random_individual() for _ in range(self.config.population_size)]
        fitness = [self._evaluate(individual) for individual in population]

        for generation in range(self.config.generations):
            LOGGER.info("开始第 %d 代迭代", generation + 1)
            # 通过精英保留直接复制部分优秀个体到下一代
            next_population: List[Dict[str, float]] = self._elitism(population, fitness)

            while len(next_population) < self.config.population_size:
                parent_a = self._select(population, fitness)
                parent_b = self._select(population, fitness)
                child_a, child_b = self._crossover(parent_a, parent_b)
                child_a = self._mutate(child_a)
                child_b = self._mutate(child_b)
                next_population.extend([child_a, child_b])

            # 若新种群超出规模，裁剪到预期数量
            population = next_population[: self.config.population_size]
            fitness = [self._evaluate(individual) for individual in population]

            if self.visualizer:
                # 将历史数据传给可视化模块绘制进度
                self.visualizer.update(generation + 1, self._history)

            LOGGER.info(
                "第 %d 代最佳 CL/CD = %.4f",
                generation + 1,
                max(entry["cl_cd"] for entry in self._history if entry["generation"] == generation + 1),
            )

        best_index = max(range(len(fitness)), key=lambda idx: fitness[idx][0])
        best_individual = population[best_index]
        best_coefficients = fitness[best_index][1]
        return best_individual, best_coefficients

    def _random_individual(self) -> Dict[str, float]:
        """生成一个随机个体，包含全部设计变量。"""

        return {var.name: var.sample() for var in self.variables}

    def _evaluate(self, individual: Dict[str, float]) -> Tuple[float, AerodynamicCoefficients]:
        LOGGER.debug("评估个体: %s", individual)
        geometry = self.generator.generate_geometry(individual)
        if geometry.mesh_path is None:
            raise RuntimeError(
                "SU2 求解需要使用网格导出文件，请在几何配置中启用 'su2' 格式。"
            )
        eval_parameters = {**individual, **geometry.metadata}
        coefficients = self.solver.evaluate_design(geometry.mesh_path, eval_parameters)
        score = self._objective(coefficients)

        record = {
            "generation": len(self._history) // self.config.population_size + 1,
            "design_id": geometry.design_id,
            "cl": coefficients.cl,
            "cd": coefficients.cd,
            "cl_cd": coefficients.cl_cd,
            **individual,
            **geometry.metadata,
        }
        self._history.append(record)
        self._append_history(record)
        return score, coefficients

    def _objective(self, coefficients: AerodynamicCoefficients) -> float:
        """根据目标函数类型计算适应度分值。"""

        if self.config.objective == "maximize_cl_cd":
            return coefficients.cl_cd
        if self.config.objective == "minimize_cd":
            return -coefficients.cd
        if self.config.objective == "target_cl":
            return -abs(coefficients.cl - self.config.target_cl)
        raise ValueError(f"Unsupported objective: {self.config.objective}")

    def _elitism(
        self, population: List[Dict[str, float]], fitness: List[Tuple[float, AerodynamicCoefficients]]
    ) -> List[Dict[str, float]]:
        """按照适应度排序并返回需要保留的精英个体。"""

        ranked = sorted(zip(population, fitness), key=lambda item: item[1][0], reverse=True)
        elite = [individual for individual, _ in ranked[: self.config.elitism]]
        LOGGER.debug("保留 %d 个精英个体", len(elite))
        return elite

    def _select(
        self, population: List[Dict[str, float]], fitness: List[Tuple[float, AerodynamicCoefficients]]
    ) -> Dict[str, float]:
        """使用锦标赛选择策略挑选父代个体。"""

        participants = random.sample(range(len(population)), self.config.tournament_size)
        best_idx = max(participants, key=lambda idx: fitness[idx][0])
        return population[best_idx]

    def _crossover(self, parent_a: Dict[str, float], parent_b: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
        """执行单点交叉，随机交换变量前后段。"""

        if random.random() > self.config.crossover_rate:
            return parent_a.copy(), parent_b.copy()
        pivot = random.randint(1, len(self.variables) - 1)
        names = [var.name for var in self.variables]
        child_a = {name: (parent_a if idx < pivot else parent_b)[name] for idx, name in enumerate(names)}
        child_b = {name: (parent_b if idx < pivot else parent_a)[name] for idx, name in enumerate(names)}
        return child_a, child_b

    def _mutate(self, individual: Dict[str, float]) -> Dict[str, float]:
        """按概率对个体变量添加高斯噪声，实现突变。"""

        mutated = individual.copy()
        for variable in self.variables:
            if random.random() < self.config.mutation_rate:
                delta = random.gauss(0.0, self.config.mutation_sigma * (variable.maximum - variable.minimum))
                mutated[variable.name] = variable.clamp(mutated[variable.name] + delta)
        return mutated

    def _append_history(self, record: Dict[str, float]) -> None:
        """将单次评估记录追加写入 CSV，便于后续分析。"""

        write_header = not self.config.history_csv.exists()
        with self.config.history_csv.open("a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=record.keys())
            if write_header:
                writer.writeheader()
            writer.writerow(record)


__all__ = ["DesignVariable", "OptimizerConfig", "GeneticOptimizer"]

