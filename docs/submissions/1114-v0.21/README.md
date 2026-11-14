# 1114-v0.21

- **日期**：2026-11-14
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：main v17 / account2 v20 admission `passed` 并激活；entry code hash `86b46df3e37a`
- **快照**：advance_holds.py, agent.py, borgo_replay.py, dust2_b_replay.py, dust2_replay.py, dust2_user_ct_routes.py, map_patches.py, mirage_replay.py, mirage_user_ct_routes.py, mirage_user_t_routes.py, molo_replay.py, nevaio_replay.py, pro_retakes.py（见同目录文件）

## 改动说明

### Dust2 CT A/B 车位用户录制路线

新增四段用户 Walklab 录制，按「走位（opening）+ 守位（hold）」配成两组 CT 防守路线：

| 名称 | 包点 | opening | hold | 帧数 |
| --- | --- | --- | --- | --- |
| `A_1` | A | `dust2 ct 走a 车位.json` | `dust2 ct 守a车位.json` | 216 / 98 |
| `B_1` | B | `dust2 ct 走b车位.json` | `dust2 ct 守b车位.json` | 312 / 230 |

- `recordings/dust2_ct/`：四份 `walklab-v2` 源 JSON（20 Hz、`defend`、`dust2-cs2-v54`、hash `b0c30852…`）与 `manifest.json`；源文件不进入提交 ZIP。
- `scripts/build_dust2_ct_routes.py`：校验格式、地图 ID/几何哈希、连续 tick、有限 pose、键位与站点配对；opening 终点与 hold 首帧偏差 0.0 m，hold 首尾闭合误差 A 0.75 m / B 1.49 m。输出 zlib + ascii85 内嵌的 `(x, y, z, yaw, pitch, key_mask)` 帧并保留每份源 JSON 的 SHA-256。
- `dust2_user_ct_routes.py`：生成本批 `PAIRS = (A_1, B_1)`；本批没有录制回防，`RETAKES = {}`。
- `agent.py`：`user_ct_routes()` 按地图 ID/静态哈希分发 Dust2 pairs，Mirage 候选保持不变。CT 防守时按所选包点取 pair：opening 跟完后切 hold 循环；遇敌暂停/续走、卡住脱困与放弃沿既有 CT 录制路线逻辑；下包后因无 Dust2 录制回防，回落到原有 A* 回防。
- `tests/test_dust2_user_ct.py`：8 项测试，覆盖清单编译、源哈希一致性、错误地图/错配守点拒绝、双图分发、按站点选路、opening→hold→下包结束、静止守点不计卡住。

## 对应规范

- [11-14-dust2-ct-car-routes.md](../../spec/11-14-dust2-ct-car-routes.md) — 数据配对、编译校验、运行时选择与待验证项。
- [Walklab route intake](../../.agents/skills/walklab-routes/SKILL.md) — 录制 JSON 的导入、校验与路线注册流程。

## 上传回执

- main：bundle `5147b1a4-deff-4c3c-bc75-cc468154ff54`，admission `passed`，version `17` 激活（entry `f81706cb-1aa5-54e6-9e4b-e1199ca25820`）。
- account2：bundle `9ecf81e4-fea8-4634-9ea6-3c300188d3d2`，admission `passed`，version `20` 激活（entry `a23486ad-a765-51b7-b2a9-b090b2d2e48f`）。
- 两个 entry 的 `code_hash_short` 均为 `86b46df3e37a`，与 ZIP SHA-256 前缀一致。

## 验证情况

- 本地 `python3 -m unittest discover -s tests -q`：195 通过、6 skipped；`git diff --check` 通过。
- 编译帧与源 JSON 逐帧比对，位置/视角最大偏差 0.0。
- 两个守点停在 A/B 车位，距夹具包点中心分别约 25.7 m / 22.8 m。
- 上传、准入与激活成功不等于完整对局、比分或胜利；实走碰撞、视线与实战效果待回填。
