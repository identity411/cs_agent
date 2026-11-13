# 1113-v0.08

- **日期**：2026-11-13（Asia/Shanghai）
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：`rsi-fps-5.5`
- **状态**：main submitted; admission passed; version 5 activated；account2 submitted; admission passed; version 7 activated
- **快照**：agent.py, advance_holds.py, map_patches.py, dust2_replay.py（见同目录文件）

## 改动

- **对枪刹停 / 点射**：`agent.py` 新增 `STOP_SPEED=1.0` 刹停门；看到敌人立即 `move_forward=0`、`move_right=0`，`grounded` 且 `speed <= 1.0` 才开火。远距离或只有头部可见时瞄头、单发点射（`TAP_INTERVAL_TICKS=15`）；近距离可见身体才扫射。`combat_move()` 移动时强制 `fire=False`。依据 `fbd4b6bf` R9：seat 0 在 CT 出生点 `(117.30,18.04)` 卡住约 28 s，tick 43618–43636 原地对 90.6 m 目标扫射 4 发，tick 44314–44326 移动中开火。详见 `docs/spec/11-13-nevaio-r9-fire-discipline.md`。
- **带包人 40 s 兜底豁免**：`ct_fallback` 追加 `not carrying_bomb`；带包人 40 s 后仍去 `plant_point(site)`，进 plant zone 直接下包，不再去 CT spawn。
- **守包不转圈**：`advance_holds.py` 新增 `PlantHold / PlantSpot / PlantLook`；`agent.py` 删除 `yaw_rate=0.15` 原地旋转，改为掩体 spot + 离散 look + dwell 循环（`post_plant_target()`）。
  - Mirage A：箱子旁 `(48.6,89.8,15.43)`，依次看 CT spawn / jungle / arch；
  - Mirage B：沙发 `(109.4,54.1,15.7)` 看 market / B short，再小 loop 到 B 小 `(98.6,50.5,15.8)` 回看 market；
  - 无 authored 数据的地图用炸弹位置/附近 patrol 点合成离散 look；10 s 未到 spot 自动降级守炸弹。
- **nevaio CT 出生点路线**：`map_patches.py` 给 `warm_hall (86,18)` 加 soft hazard；`agent.py` 每回合清临时 `edge_penalty` 后重新应用永久 hazard。真实 nav 复盘：R7/R9 的旧惩罚会把 CT→B 推回 warm_hall 西出口；修复后走 `ct → rear_corner → rear_door → B`，CT→A 不变。
- **文档**：新增 `docs/spec/11-13-nevaio-r9-fire-discipline.md`、`docs/spec/11-13-post-plant-holds.md`，并更新 spec 索引 / pathing / advance-holds 记录。

## 验证与限制

- 全量 unittest 75/75 通过；`py_compile`、`git diff --check` 通过。
- 本地真实 static 验证：nevaio CT 出生点 → B nav 模拟 23.7 s reached；T 带包 → B 44.7 s reached（route `B_drill`，未走 CT spawn）；Mirage A/B hold spot 可从 T spawn 到达。
- **未验证**：Mirage 守包 spot 的真实碰撞/LOS、A 箱子 spot 与 B 沙发/B 小是否有遮挡、下一场正式对局的站定开火占比与远距离命中。
- 只有正式对局回放能验证效果；上传/准入/激活成功不代表比分或排名。

## 提交

- ZIP SHA-256：`4f12f28d10b79ebbd486f101123bc0865a1270220f2393bce352220eff33a4fa`（47,979 B，4 个文件）。
- `main`：agent `11a0f0db-afda-4a57-a2f4-36ed0462085e`，bundle `6c996008-5281-4bee-bef6-90ccce9c5769`，admission `passed`，version 5 `f70ea21d-dc5e-4766-99d3-34c1eaa3d9e6` 已激活，entry code hash `4f12f28d10b7`。
- `account2`：agent `291c135e-e580-4762-b007-906a0fb742df`，bundle `dea5b55f-3884-4840-92c3-be29d17938b7`，admission `passed`，version 7 `273cd05e-cb99-4a99-9a15-1e52088ad398` 已激活，entry code hash `4f12f28d10b7`。
- 回执：`/tmp/agx-receipt-v008.json`。

## 对应规范

- `docs/spec/11-13-nevaio-r9-fire-discipline.md`
- `docs/spec/11-13-post-plant-holds.md`
- `docs/spec/11-12-advance-holds.md`
- `docs/spec/11-12-pathing-routes.md`

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；上传/准入/激活成功不代表完整对局、比分或排名。
