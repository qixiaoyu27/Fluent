# Fluent
气动实验

## 全自动流程

项目提供 ``src/main.py`` 作为入口脚本，串联 ``cadquery`` 建模、``Gmsh`` 网格划分、
``SU2`` 求解与 ``matplotlib`` 后处理。所有关键参数均集中在 ``src/config.yaml`` 中，
可根据需求修改巡航工况、网格尺寸或边界条件。

### 运行步骤

```bash
python src/main.py
```

### 依赖软件

- [cadquery](https://cadquery.readthedocs.io/en/latest/)
- [Gmsh](https://gmsh.info/)
- [SU2](https://su2code.github.io/)
- [matplotlib](https://matplotlib.org/)

请在 ``config.yaml`` 中确认 SU2 可执行文件路径、网格参数及飞行工况配置，所有
结果分别输出至 ``result/model``、``result/mesh`` 与 ``result/cfd`` 目录。
