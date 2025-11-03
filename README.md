# Fluent

气动实验

## 全自动整流罩 CFD 流程

本工程提供一个基于 Python 的端到端自动化流程，涵盖整流罩建模、网格划分、SU2 求解和后处理。所有参数集中在 `src/config.yaml` 中配置，便于记录与复现。

### 目录结构

```
Fluent/
├── lib/                    # SU2 配置模板等外部资源
├── result/                 # 自动生成的模型、网格和 CFD 结果
├── src/
│   ├── cfd/                # SU2 调用与历史解析
│   ├── mesh/               # Gmsh 网格生成脚本
│   ├── model/              # CadQuery 几何建模脚本
│   ├── postprocess/        # 后处理模块
│   ├── config.yaml         # 全局配置文件
│   └── pipeline.py         # 主流程入口
└── README.md
```

### 使用方法

1. 确保安装 Python 3.9+，并安装依赖：
   ```bash
   pip install cadquery gmsh matplotlib pandas pyyaml
   ```

2. 根据实际环境修改 `src/config.yaml` 中的参数（特别是 SU2 可执行文件路径和网格尺寸设定）。

3. 运行完整流程：
   ```bash
   python -m src.pipeline
   ```

4. 生成的模型、网格和 CFD 结果分别保存在 `result/model`、`result/mesh`、`result/cfd` 目录下。

### 注意事项

- 建模阶段采用 CadQuery 参数化建模，可通过配置文件快速调整尺寸比例。
- 网格划分基于 Gmsh 的 Python API，默认会添加边界层控制，具体厚度和层数可调。
- 气动计算使用 SU2，需提前在本机安装，并在配置文件中指明可执行文件路径。
- 后处理阶段使用 Matplotlib 绘制升阻力系数和残差曲线，并输出 JSON 摘要，便于科研汇报。

如需扩展更多后处理指标，可在 `src/postprocess/analyze.py` 中添加自定义逻辑。
