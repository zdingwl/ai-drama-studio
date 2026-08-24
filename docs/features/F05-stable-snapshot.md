# F05 Stable Snapshot — 镜头人工修正 / 三栏拉片工作台

状态：`STABLE / FROZEN`
冻结日期：2026-08-24

## 1. 冻结结论

F05 已由用户在 Windows 本机真实项目中完成三栏工作台验收并执行 Final Shots 确认。

冻结后，后续 Feature 只能依赖这里的 Final Shot Contract，不得静默改变 F05 时间语义、ID 语义或覆盖 F04 Auto Evidence。

## 2. 上游来源

```text
F04 shot_candidates
→ F05 initialize
→ shot_edit_sets
→ final_shots
```

F04 `shot_candidates.detected_*` 永远保持只读 Auto Evidence。

F05 初始化后保存：

```text
source_detection_id
```

因此 Final Shot 可以追溯到其来源的 F04 Detection Run。

## 3. Final Shot 稳定身份

生产级镜头 ID：

```text
SHOT_<UUID4>
```

规则：

- 普通边界微调不改变 Final Shot ID；
- 拆分时原 ID 保留给左段，新建右段 ID；
- 合并时保留左段 ID，删除右段 ID；
- 后续人物、对白、Scene、镜头语义、生成、QC 应关联 Final Shot ID，而不是 F04 Candidate ID。

## 4. 时间 Contract

权威时间单位：

```text
Source Domain integer microseconds
```

区间：

```text
[start_us, end_us)
```

完整时间轴必须满足：

```text
first.start == edit_set.source_start_us
last.end == edit_set.source_end_us
prev.end == next.start
ordinal == 1..N
无 gap
无 overlap
```

移动一个公共边界时必须同时更新：

```text
left.final_end_us
right.final_start_us
```

播放器 / FFmpeg 媒体相对时间：

```text
relative_seconds = (source_us - edit_set.source_start_us) / 1_000_000
```

禁止把 Source absolute timestamp 直接当浏览器 `video.currentTime`。

## 5. Database

Migration：

```text
0006_create_final_shots
```

冻结表：

```text
shot_edit_sets
final_shots
```

Edit Set 状态：

```text
editing
confirmed
```

一旦进入 `confirmed`：

- 边界修改拒绝；
- 拆分拒绝；
- 合并拒绝；
- Final Shot Timeline 作为后续 Feature 稳定输入。

## 6. Backend 冻结职责

核心：

```text
engine/app/shot_workbench.py
```

公开业务函数：

```text
initialize_shot_workbench()
get_shot_workbench()
adjust_shot_boundary()
split_final_shot()
merge_final_shots()
confirm_final_shots()
get_workbench_proxy_path()
render_workbench_frame()
```

这些函数不得扩展成 F06+ 的人物识别、对白识别、Scene/VLM 或生成逻辑。

## 7. API

```text
GET  /api/projects/{project_id}/shot-workbench
POST /api/projects/{project_id}/shot-workbench/initialize
POST /api/projects/{project_id}/shot-workbench/boundary
POST /api/projects/{project_id}/shot-workbench/split
POST /api/projects/{project_id}/shot-workbench/merge
POST /api/projects/{project_id}/shot-workbench/confirm
GET  /api/projects/{project_id}/shot-workbench/media/proxy
GET  /api/projects/{project_id}/shot-workbench/frame?source_time_us=...
```

## 8. Frontend 冻结交互

Route：

```text
/projects/:projectId/shot-workbench
```

三栏结构：

```text
左：Final Shot 列表 / 缩略图 / 时间 / 当前 Shot 高亮
中：Proxy 播放器 / Shot Timeline / 5 关键帧
右：Final Start/End / 拆分 / 合并 / 来源追溯 / 确认
```

已确认交互：

- 点击 Shot 跳转播放器；
- 播放跨镜头时当前 Shot 自动高亮；
- 当前 Shot 自动滚动到左侧可见区域；
- 缩略图采用镜头中间位置，预览按队列生成并缓存；
- 关键帧为首 / 25% / 中 / 75% / 尾，并避开精确切点边缘；
- 拆分 = 新增镜头；
- 合并 = 删除公共边界；
- 最终确认后进入只读锁定。

## 9. Scope Boundary

F05 不负责：

```text
人物识别
角色身份
Whisper ASR
说话人绑定
场景识别
景别/机位/运镜/动作 VLM 分析
生成 Prompt
视频生成
QC
```

这些能力由 F06+ 后续 Feature 在 Final Shot ID 上继续建设。

## 10. Freeze Rule

从本 Snapshot 生效后：

```text
F05 = STABLE / FROZEN
```

如后续发现 F05 缺陷，只允许做兼容性修复；任何改变 Final Shot ID、Source Timeline、confirmed 锁定语义、F04 Auto Evidence 只读规则的改动，必须先解除冻结并重新评审 Contract。
