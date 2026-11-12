# 1113-v0.05

- **日期**：2026-11-13（Asia/Shanghai）
- **比赛 ID**：`2a97f94f-816a-52b7-b4b8-5925db160245`
- **合同**：rsi-fps-5.5
- **状态**：account2 submitted; admission passed; version 4 activated
- **快照**：agent.py, dust2_replay.py, map_patches.py（见同目录文件）

## 改动

- 将用户录制的 Dust2 20Hz、2002 帧轨迹编译为 `dust2_replay.py`，保留每帧位置、yaw/pitch 与 WASD/Shift 状态。原录制 SHA-256 为 `57473976cda44efc04ebfa9feefe348754b88ea479f21c00eda716871d801e9e`。
- 仅在地图 ID 和静态哈希均匹配 `dust2-cs2-v54`、T 方进攻且炸弹未安装时启用。轨迹进度按比赛实时位置推进；准星与世界移动分开纠偏，不按录制时间直接回放动作。
- 可见敌人时冻结轨迹进度并停止移动，使用原有瞄准射击；敌人消失后接回轨迹。偏离轨迹超过 6 米时使用原有导航寻路到录制路线，避免直接穿越障碍。
- 录制末端的静止尾帧完成后，恢复原有到点、下包和守包逻辑。

## 验证与限制

- 导航/录制相关 unittest 30/30 通过。全量测试 54 项通过，另 3 项账户 HTTP 模拟测试因本地端口绑定被沙箱禁止而未运行。
- 无碰撞运动学模拟：B 点约 94.6 秒进入范围，A 点约 109.9 秒进入范围；2.4、3.0、3.6 m/s 的独立轨迹跟踪均接近录制终点。正式比赛碰撞、交火和队友阻挡仍需真实对局验证。
- 录制轨迹的末端靠近 B 点，并非 A 小终点。由于要求使用完整录制轨迹，Dust2 T 方 A 目标也先走该轨迹，A 点剩余时间较少。

## 提交

- 仅提交 `account2`，FPS 合同 `rsi-fps-5.5`。ZIP SHA-256 `b91f85504c7bbc4f7bb506388010906b151e7c744f5f7eb2cc6bbb313d416e56`。
- bundle `1629385a-e2d2-43ed-bd58-acbc6de12153`，admission `passed`；account2 version 4 `0c377bab-0d2d-418d-90e3-d48f3f7e6eb7` 已激活，entry code hash `b91f85504c7b`。

## 对应规范

[Dust2 进攻路线与移动控制](../../spec/11-12-pathing-routes.md)。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
