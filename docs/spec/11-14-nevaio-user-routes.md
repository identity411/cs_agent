# 规范：Nevaio 用户录制 T 进攻 / CT 开局与回防路线

Status: **2026-11-14 已编译并注册，随 `1114-v0.22` 提交并激活（`main` v18 / `account2` v21，admission `passed`，entry code hash `b2f874a6d0df`）；全量单元测试通过。CT 守点采用末帧静止守点，不是独立守点录制。尚未在正式对局实走验证。**
Date: 2026-11-14
Related: [路径与控制](./11-12-pathing-routes.md) · [T 方多路线轮换](./11-13-t-route-rotation.md) · [职业 demo 到 agent 跟随](./11-14-pro-demo-walklab-pipeline.md) · [Walklab route intake](../../.agents/skills/walklab-routes/SKILL.md)

## 1. 来源

12 条 `walklab-v2` 记录，均为 `nevaio-r3-v54`、几何哈希 `78137c32…9e67e3`、20 Hz、tick 连续。原始导出没有 `side` / `purpose` / `targetSite` 字段，角色由 manifest 明确指定；文件名只作为稳定 ID。

原始 JSON 保存在 `recordings/nevaio_t/` 与 `recordings/nevaio_ct/`；微信传输文件名带 `(1)` 后缀，保存时去掉，文件内容未改动。编译模块的 `sha256` 字段记录源文件哈希。

| 文件 | 角色 | 帧数 | 终点 |
| --- | --- | --- | --- |
| `nevaio-walk-t-a-mid.json` | T → A，mid | 1069 | A 点 0.7 m |
| `nevaio-walk-t-a-long.json` | T → A，long | 679 | A 点 2.7 m |
| `nevaio-walk-t-b-mid.json` | T → B，mid | 990 | B 点 2.4 m |
| `nevaio-walk-t-b-long.json` | T → B，long | 590 | B 点 2.5 m |
| `nevaio-walk-ct-a-mid.json` | CT 开局 → A，mid | 832 | A 点 0.5 m |
| `nevaio-walk-ct-a-long.json` | CT 开局 → A，long | 506 | A 点 3.2 m |
| `nevaio-walk-ct-b-mid.json` | CT 开局 → B，mid | 642 | B 点 5.9 m |
| `nevaio-walk-ct-b-long.json` | CT 开局 → B，long | 397 | B 点 3.6 m |
| `nevaio-walk-a-b-mid.json` | CT 回防 A → B，mid | 749 | B 点 2.8 m |
| `nevaio-walk-a-b-long.json` | CT 回防 A → B，long | 803 | B 点 1.8 m |
| `nevaio-walk-b-a-mid.json` | CT 回防 B → A，mid | 686 | A 点 0.4 m |
| `nevaio-walk-b-a-long.json` | CT 回防 B → A，long | 745 | A 点 2.1 m |

外部提供的 `nevaio_replay(1).py` 已逐帧核对：12 条位置、yaw/pitch、按键 mask 与上述原始 JSON 完全一致，`source_sha256` 与源文件 SHA-256 一致。本次接入不直接依赖该文件，而是由 manifest + 编译器从原始 JSON 重新生成。

## 2. Manifest 与编译

- `recordings/nevaio_t/manifest.json`：4 条 T 进攻，声明 `name`、`site`、`via`、`source`。
- `recordings/nevaio_ct/manifest.json`：4 条 CT 开局（`hold: null`、`holdMode: "final_pose"`）与 4 条回防（声明 `origin` / `target`）。

编译命令：

```text
python3 -m scripts.build_nevaio_routes t  recordings/nevaio_t/manifest.json  walklab/src/map-fixtures/nevaio_static.json nevaio_user_t_routes.py
python3 -m scripts.build_nevaio_routes ct recordings/nevaio_ct/manifest.json walklab/src/map-fixtures/nevaio_static.json nevaio_user_ct_routes.py
```

编译器校验：

- `format == walklab-v2`、地图 ID / 几何哈希精确匹配、20 Hz、tick 从 0 连续；
- 位置和 yaw/pitch 有限、按键属于 `KEY_BITS`、轨迹确有位移；
- T 路线目标包点合法，`carrier_cutoff` 是距包点中心 ≤12 m 的第一帧，且最后一帧仍在 12 m 内；
- CT 开局终点在目标包点 12 m 内；回防起点/终点分别在 origin/target 包点 12 m 内；
- 同一 manifest 内文件名唯一且不得包含路径，防止重复或越界读取。

`carrier_cutoff` 沿用现有语义：带包者跟到截止帧或实时距离 ≤12 m 时退出录制轨迹，转 A* 下包。非带包者跟随完整路线。`POSTPLANT` 目前为空，T 下包后仍使用既有 post-plant 逻辑。

## 3. 注册与运行时行为

`agent.py` 的 `user_t_routes()` / `user_ct_routes()` 增加 Nevaio 分支，只在 ID 与几何哈希同时匹配时返回数据。

- T：`recorded_route_options()` 先保留 `legacy`（旧 A 路线），再按 manifest 顺序追加 `A_mid`、`A_long`、`B_mid`、`B_long`。选路仍先由 `choose_site()` 决定包点，再在该站点的候选中按现有失败权重轮换；B 点首次拥有录制进攻路线。
- 旧 `nevaio_replay.py` 的 `SITE = "A"` 原本让 `recorded_site()` 把 T 计划固定在 A。用户候选同时覆盖 A/B 后，`recorded_site()` 对 Nevaio 返回 `None`，改由现有 `choose_site()` 的队友/带包者/回合逻辑选点；A 回合有 3 条候选，B 回合有 2 条。
- CT 开局：`choose_ct_recorded()` 按站点过滤，并以 `seat % len(options)` 在 mid/long 间分散。
- CT 回防：`choose_retake()` 直接消费 `A_to_B` / `B_to_A` 两组录制回防；进入范围判断、A* 接回和到点逻辑与 Mirage 用户回防一致。

`recorded_route_options()` 的用户路线追加已从 Dust2/Mirage 专用分支收敛为通用逻辑：Dust2 仍保持 `legacy → B_site_20261113 → B_mid_doors_20261114`，Mirage 候选顺序不变，其他地图在 `user_t_routes()` 返回空时不产生变化。

## 4. CT 末帧静止守点

这批录制只有从 CT 出生点到包点的开走段，没有独立的守点循环。用户选择的行为是**末帧静止守点**：

- 编译时 `hold` 为单帧，内容等于 opening 的最后一帧，`holdMode` 为 `final_pose`；
- 开走段结束后 `follow_ct_recorded()` 切入 hold 阶段，站在原地保持录制终点的位置与视角；
- 敌人可见时仍由既有战斗逻辑优先接管；炸弹下包后退出守点并进入回防选择。

这是运行时行为约定，不是守点录制：没有验证末帧位置是否适合架枪、是否有掩体或是否会被对手预瞄。后续若补录真实守点，在 `recordings/nevaio_ct/manifest.json` 中把对应 `hold` 改为文件名并去掉 `holdMode`，重新编译即可走现有 `opening → hold loop` 校验（接点 ≤0.2 m、循环首尾 ≤1 m）。

## 5. 验证与边界

- 新增 `tests/test_nevaio_user_routes.py`：manifest 编译、地图哈希拒绝、T 截止帧、站点过滤、legacy 保留、CT mid/long 选择、末帧 hold、双向回防注册、错误哈希禁用。
- `python3 -m unittest discover -s tests -q`：219 个测试通过（6 个跳过）。
- 编译与单元测试只证明数据接通和选择逻辑；门洞、台阶、坡面、掩体碰撞、末帧守点是否可实战均未验证。上传、准入与激活成功不等于完整对局或胜利，实战效果待 `agx-match-query` 回填。
