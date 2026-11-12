# 1112-v0.00 — baseline

- **日期**：2026-11-12
- **源码提交**：`57fb246`（"Add rule-based baseline FPS agent"）
- **合同**：官方 `rsi-fps-5.5` 之前；未按官方合同校验
- **状态**：baseline，未上传
- **快照**：[`agent.py`](agent.py)，sha256 `eb94b88e287d62ebb858cc0b29134dd1f1e39c3d5e4b8b388fb7bb15d545018e`

## 改动说明

初始 baseline：地图 BFS 寻路、购买、几何瞄准射击、下包 / 拆包与卡住恢复。代码按原 177 行 starter 还原，未针对官方合同 `rsi-fps-5.5` 做适配。

## 对应规范

- [`docs/spec/baseline-compatibility.md`](../../spec/baseline-compatibility.md) — 记录本版本与官方合同的差异和修改优先级。
- 本版本**未**验证 `map.nav`、`aim_punch`、`reload_until`、下包 / 拆包条件等关键假设；详见上述规范。

## 验证情况

- 仅做过静态审阅；未运行官方本地 probe，未取得上传准入或完整对局回执。
- 因此不能把本快照视为符合 `rsi-fps-5.5` 的实现。

## 后续

下一次提交前，先按 `baseline-compatibility.md` 的优先级修正，并在 `docs/submissions/` 新增 `MMDD-vX.YY/` 快照与改动说明。
