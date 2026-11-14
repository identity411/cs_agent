# 1114-v0.19

- **日期**：2026-11-14
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 15 activated · account2 submitted; admission passed; version 18 activated
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, mirage_user_ct_routes.py, mirage_user_t_routes.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

### 通用轨迹链接器（P1，见 [11-14-route-linker.md](../../spec/11-14-route-linker.md)）

- 新增 `agent.link_to_route()`：从当前/上一段轨迹终点用 A* 走向下一段入口，距入口 ≤6 m 后切换为轨迹跟随；不再使用直线转向，`retake_direct()` 已移除。
- 允许中途进入轨迹：`choose_route_entry()` 按当前位置取最多 4 个、间隔 ≥24 帧的候选入口，并补上第 0 帧；对每个候选跑 A*，取路径代价最小的可达帧。入口不需要是第 0 帧。
- CT 守点 → 回防接入：下包后 3 s 内可重复选路；origin site 或距轨迹 20 m 内均可接路；8 s 接路超时；卡住/超时后按候选入口重试，全部失败回退 A* 到炸弹。
- 原地转向不计为卡住（`_retake_turning()`）；回防末帧后改用 A* 到炸弹；同点下包记录 `same_site`，不走跨点回防；下包时保留 `ct_recorded_pair` 供交接日志使用。
- 新增 stderr 日志：`link ... pair=... retake=... mode=astar result=... entry=.../... join_dist=...`。
- Mirage B_1/B_2/B_3 实测分别命中回防轨迹第 38/38/31 帧；B_2 用 A* 接路，B_1/B_3 当拍进入。

### Mirage CT 守点 B_3 禁用

- 新增 `MIRAGE_DISABLED_CT_PAIRS = frozenset({"B_3"})`；B 点 two-box 攀爬在平台碰撞中不可通过，`choose_ct_recorded()` 不再给 B 守点分配 B_3，回退到 B_1/B_2。新增测试 `test_b_two_box_route_is_not_selected_for_matches`。

### 验证

- 本地 `python3 -m unittest discover -s tests -q`：**177/177** 通过（6 skipped）。
- 新增 `tests/test_route_linker.py`（10 个用例）覆盖 A* 接路、入口半径、选路重试、中途进入、决策窗口、同点下包、转向不判卡住、末段 A* 到炸弹。
- 上传回执：`main` admission `passed`，version 15 activated；`account2` admission `passed`，version 18 activated；entry code hash `55bff79bffe0`。
- admission/激活不等同于完整对局、得分或胜负；链接耗时、入口帧分布、回防到位率仍需下一场正式对局回填。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
