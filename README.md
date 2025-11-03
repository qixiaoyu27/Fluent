# Fluent

气动实验

## 自动化流程

项目提供 `python -m src.main` 入口脚本，根据 `src/config.yaml` 中的参数依次完成以下步骤：

1. **建模**：调用 CadQuery 按配置生成整流罩几何并导出至 `result/model` 目录。
2. **网格划分**：借助 Gmsh 导入 STEP 几何，自动构造远场域并导出 SU2 网格到 `result/mesh`。
3. **气动计算**：依据配置生成 SU2 配置文件，可选择是否自动调用 `SU2_CFD.exe` 并输出到 `result/cfd`。
4. **后处理**：当启用 `execution.run_post` 时，解析 SU2 结果并绘制历史曲线、生成概要报告。

> **提示**：默认配置下 `execution.run_solver` 关闭，可在具备 SU2 环境时将其改为 `true` 以触发求解。
