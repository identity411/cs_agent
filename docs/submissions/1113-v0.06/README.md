# 1113-v0.06

- **日期**：2026-11-13（Asia/Shanghai）
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：account2 submitted; admission passed; version 5 activated
- **快照**：agent.py, dust2_replay.py, map_patches.py（见同目录文件）

## 改动

- 在 `1113-v0.05` 的 Dust2 录制轨迹闭环跟随上，新增同坐标静止帧的逐拍推进：原地预瞄时不提前移动，准星 yaw/pitch 仍按录制的 20Hz 帧序列纠偏。
- 保留地图 ID/哈希门控、位置纠偏、可见敌人时停止并射击、失去可见敌人后接回原轨迹、偏离过大时 A* 接回，以及轨迹终点后原有到点逻辑。

## 验证与限制

- 全量 unittest 59/59 通过；`py_compile` 和 `git diff --check` 通过。
- 无碰撞运动学模拟：B 点约 95.5 秒进入范围，A 点约 110.9 秒进入范围。录制终点靠近 B 点，A 点目标经过 B 侧轨迹后剩余时间很少；正式比赛的碰撞、敌人和队友影响尚未由完整对局验证。

## 提交

- 仅提交 `account2`，FPS 合同 `rsi-fps-5.5`。ZIP SHA-256 `c00849609e14a7075fbc1778dd4434719eb584fdea392c335e2a5d53865318c1`。
- bundle `027acf03-77f5-4ab4-8cbb-8e5a01274cb3`，admission `passed`；account2 version 5 `6723380e-ee2d-4ebc-8a2a-b6bc4579fa37` 已激活，entry code hash `c00849609e14`。

## 对应规范

[Dust2 进攻路线与移动控制](../../spec/11-12-pathing-routes.md)。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
