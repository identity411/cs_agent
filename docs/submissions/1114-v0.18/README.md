# 1114-v0.18

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：unknown
- **状态**：main submitted; admission passed; version 14 activated · account2 submitted; admission passed; version 17 activated
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, mirage_user_ct_routes.py, mirage_user_t_routes.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

# 1114-v0.18

- **日期**：2026-11-13
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main submitted; admission passed; version 14 activated · account2 submitted; admission passed; version 17 activated
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, map_patches.py, mirage_replay.py, mirage_user_ct_routes.py, mirage_user_t_routes.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

### 后坐力、掉包恢复与购买（见 [11-14-recoil-bomb-economy.md](../../spec/11-14-recoil-bomb-economy.md)）

- `combat()` 改读合法字段 `recoil_yaw` / `recoil_pitch`，按官方 baseline 的 2 倍偏移补偿；对准判定使用补偿后误差。
- 仅 T 方、未携包且观测到 `bomb.state == "dropped"` 时启动掉包恢复：暂时停用录制路线与 via 点，用 A* 接近炸弹；自己拾取后直接寻路下包，队友拾取后赶往包点支援；中断路线不计成功权重。
- 购买改为每拍一件：缺步枪且买得起先买步枪；护甲 <50 时买护甲；缺头盔按满甲 350 / 否则 1000 的预算门槛购买；最后 CT 补拆弹器。

### Mirage 用户录制 CT 路线与职业 demo T 路线（见 [11-14-pro-demo-walklab-pipeline.md](../../spec/11-14-pro-demo-walklab-pipeline.md)）

- `mirage_user_ct_routes.py`：A/B 各三组 `opening → hold` 配对，加两条 B→A 回防；按地图 ID/hash 精确门控。CT 未下包时执行开局与守点循环，遇敌交给现有战斗逻辑，下包后仅匹配的用户录制回防可用。
- `mirage_user_t_routes.py`：五条经用户按 route ID 指定的 Mirage T demo 路线（A 二楼、拱门夹 A、A 大、B 小、B 二楼，含手录 B 二楼跳下衔接）与一条 A 守包片段；保留 16 Hz 原始位置/视角，不伪造键鼠输入。带包者仍在距目标包点 12 m 内切换 A* 下包，守包片段只在观察到 A 点已下包后启动。
- 两台生成器（`scripts/build_mirage_ct_routes.py`、`scripts/build_mirage_t_routes.py`）改为把 `frames` 以 zlib + ascii85 内嵌，模块 import 时解码为原有 tuple 结构；逐帧数值与 4 位小数精度不变。`mirage_user_ct_routes.py` 310,639 → 65,779 B，`mirage_user_t_routes.py` 179,056 → 53,122 B，根目录源码合计 709,516 B，满足单文件 256 KiB、总量 1 MiB 限制。

## 对应规范

- [11-14-recoil-bomb-economy.md](../../spec/11-14-recoil-bomb-economy.md) — 后坐力补偿、掉包恢复与购买预算。
- [11-14-pro-demo-walklab-pipeline.md](../../spec/11-14-pro-demo-walklab-pipeline.md) — 从 Walklab review JSON 到 agent 路线注册的完整链路。
- [11-12-pathing-routes.md](../../spec/11-12-pathing-routes.md) — 地图加载与 A* 寻路。
- [11-13-t-route-rotation.md](../../spec/11-13-t-route-rotation.md) — T 方多路线权重轮换。
- [11-13-pro-demo-routes.md](../../spec/11-13-pro-demo-routes.md) — 职业 demo CT 回防路线。

## 验证情况

- 本地 `python3 -m unittest discover -s tests` **160/160** 通过（6 skipped）；新增 `tests/test_immediate_fixes.py`、`tests/test_mirage_user_ct.py`、`tests/test_mirage_t_routes.py`。
- 路线模块重新生成后，解码结果与编译结果逐帧、逐字段一致；测试继续覆盖门控、配对、回防切换与守包启动。
- `metadata.json` 记录上传回执：两份包 admission 均 `passed` 并激活。admission 通过不等于完整对局、得分或胜负；实战效果待下一场回填。

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
