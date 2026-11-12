# 文档

本目录保存本仓库（FPS「多人枪战：爆破模式」agent）的开发参考。

| 目录 | 内容 |
| --- | --- |
| [`spec/`](spec/README.md) | 技术规范：合同、观测 / 动作、地图、目录、预算与提交 |
| [`rules/`](rules/README.md) | 比赛规则：平台参赛规则、赛制、回合、经济、目标与投掷物 |
| [`submissions/`](submissions/README.md) | 每次提交的完整代码快照、改动说明与元数据 |

## 资料状态

- `rules/platform.md`：据 AGX 官网「新手入门」页（2026-11-12）整理。
- `rules/fps-bomb.md`、`rules/utilities.md` 与 `spec/` 下的合同文档：据 AGX「多人爆破 · AI 助手开发指南」，合同 `rsi-fps-5.5`（2026-11-12 版）整理。
- 官方指南声明这是**闭门候选合同**，不表示赛事已开放；历史对局保留自己的合同。
- [`spec/baseline-compatibility.md`](spec/baseline-compatibility.md) 记录当前 `agent.py` 与该合同的差异。修正前不要假设 baseline 可直接使用。

官方完整目录、`map.nav` 实际结构与正式赛事启用状态仍待核实；见 [`spec/README.md`](spec/README.md) 的待补清单。
