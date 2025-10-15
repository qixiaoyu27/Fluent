# Fluent UAV Optimisation Pipeline

该项目提供了一套利用 OpenVSP Python API 生成小型固定翼无人机几何，并调用 SU2 自动划分网格与求解气动特性（CL、CD 以及 CL/CD）的优化框架。系统以遗传算法为核心迭代优化设计参数，并在每一代生成实时性能可视化图像。

## 功能概览

- **参数化几何建模**：基于 `config/params.yaml` 中的设计变量范围，通过 OpenVSP Python API 自动生成 VSP3 几何，同时可选导出 STL 与 SU2 网格文件。
- **SU2 气动求解**：利用模板配置文件自动渲染 SU2 输入，执行求解并解析 `history.csv` 与 `forces_breakdown.dat` 中的升力、阻力等系数。
- **遗传算法优化**：支持自定义种群规模、交叉/变异概率、适应度目标（最大化 CL/CD、最小化 CD 或逼近目标 CL）。
- **实时可视化**：每一代优化结束后生成 CL/CD 曲线图，保存到 `results/plots` 目录，便于跟踪收敛情况。
- **结果管理**：自动记录每一次评估的详细数据到 CSV，输出最佳设计摘要以及生成的几何/网格文件。

## 环境要求

- 已安装并可通过 Python 调用的 OpenVSP（需启用 Python API）。
- SU2 可执行程序（默认路径：`D:/workspace/pycharm/Fluent/SU2/SU2_CFD.exe`）。
- Python 3.10+，并安装依赖库：`pyyaml`、`matplotlib`。根据实际需求可增加 `numpy` 等科学计算包。

> **提示**：如 OpenVSP Python 模块无法直接导入，可在 `config/params.yaml` 的 `paths.openvsp_python` 字段中指定其 Python 绑定所在目录。

## 快速开始

1. **配置设计空间**：编辑 `config/params.yaml`，设置几何变量范围、优化参数和 SU2 模板路径等信息。
2. **准备 SU2 模板**：根据案例需求更新 `config/su2_template.cfg` 中的网格、边界条件等参数；模板支持 `{mesh_filename}`、`{mach_number}`、`{angle_of_attack}` 等占位符。
3. **运行优化**：
   ```bash
   python -m src.main --config config/params.yaml
   ```
4. **查看结果**：
   - 几何与网格：`results/geometry/`
   - 优化历史：`results/optimization_history.csv`
   - 最佳设计摘要：`results/best_design_summary.yaml`
   - 性能曲线：`results/plots/`

## 目录结构

```
config/
  params.yaml           # 主配置文件
  su2_template.cfg      # SU2 模板配置
results/
  geometry/             # 自动生成的 VSP3/STL/SU2 文件
  plots/                # 每代优化的性能图
src/
  main.py               # 管道入口
  model_generator.py    # OpenVSP 几何生成
  su2_interface.py      # SU2 求解封装
  optimizer.py          # 遗传算法逻辑
  visualizer.py         # 实时可视化工具
```

## 自定义扩展

- **添加新的设计变量**：在 `params.yaml` 的 `design_variables` 中增加条目，并在 `model_generator.py` 中处理相应几何参数。
- **替换求解器**：若需引入 XFOIL 等其他分析工具，可在 `su2_interface.py` 中扩展相应的接口调用和结果解析逻辑。
- **高级优化策略**：可以在 `optimizer.py` 中替换或增强遗传算法，例如加入自适应变异率、并行评估等。

## 调试建议

- 在首次运行前，可先将 `optimizer.generations` 与 `population_size` 设置较小值，以验证流程正确性。
- 通过 `logs` 目录或控制台输出监控 SU2 求解日志，若遇到求解失败可检查生成的配置与网格文件。

祝科研顺利，优化愉快！

