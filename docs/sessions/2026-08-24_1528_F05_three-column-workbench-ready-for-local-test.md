# F05 三栏拉片工作台开发完成，进入本机测试

时间：2026-08-24 15:28 +08:00  
分支：main

## 用户最新确认

用户参考其它拉片产品后确认：

```text
F04 保持自动切镜底层能力
F05 不做普通表格页
F05 改为三栏真正拉片工作台
```

随后明确指令：

```text
开始
```

因此本轮直接开始 F05。F04 仍未伪造为 Frozen；用户允许提前开发 F05。

---

## F04 当前真实验收状态

用户真实视频第一次自动拉片成功：

```text
Shot Candidates: 31
Cuts: 30
PTS Aligned Frames: 1659
Source Range: 66.360s
```

第一次保存的 Detection Runtime：

```text
PyTorch 2.5.1+cpu
Device cpu
```

用户随后在项目 venv 实际确认：

```text
torch: 2.5.1+cu124
cuda: True
cuda version: 12.4
gpu: NVIDIA GeForce RTX 3060 Ti
```

F04 已有显式安全 rerun，但用户尚未反馈 rerun 后页面实际保存 `cuda`。所以：

```text
F04 READY_FOR_REVIEW
F04 NOT FROZEN
```

### 重要顺序

F05 初始化后会永久记录 `source_detection_id` 作为 Final Shot 的 Auto Evidence 来源。为了不让 F04 重跑破坏追溯，本轮增加：

```text
存在 shot_edit_sets
→ F04 rerun 返回 SHOT_DETECTION_RERUN_CONFLICT
```

因此同一项目如果还要验证 F04 CUDA，必须：

```text
先 F04 CUDA rerun
再第一次进入 F05
```

---

# 本轮完成内容

## Contract / Docs

新增：

```text
docs/features/F05-shot-workbench.md
docs/features/F05-function-contracts.md
docs/features/F05-database-dictionary.md
```

更新：

```text
docs/PROJECT_STATE.md
docs/ENVIRONMENT_BASELINE.md
```

环境基线已经纠正为用户实际 GPU `NVIDIA GeForce RTX 3060 Ti`；未实测 VRAM，因此没有猜测显存数字。

## Database

新增：

```text
0006_create_final_shots
shot_edit_sets
final_shots
```

F04 `shot_candidates` 保持只读 Auto Evidence。

Final Shot：

```text
SHOT_<UUID4>
```

是后续人物、对白、Scene、生成、QC 应关联的稳定生产身份。

Edit Set：

```text
editing
confirmed
```

confirmed 后 F05 写操作锁定。

## Backend

新增：

```text
engine/app/shot_workbench.py
```

核心职责：

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

时间仍为：

```text
Source Domain integer microseconds
[start_us, end_us)
```

公共边界编辑同时修改左右 Shot，禁止 gap / overlap。

拆分：原 ID 留给左段，新 ID 给右段。  
合并：保留左 ID，删除右 ID。  
来源 Candidate ID 始终可追溯。

## API

新增：

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

FastAPI app version推进为 `0.5.0`。

## Frontend

新增：

```text
frontend/src/types/shot-workbench.ts
frontend/src/api/shot-workbench.ts
frontend/src/stores/shot-workbench.ts
frontend/src/views/ShotWorkbench.vue
frontend/src/shot-workbench.css
```

更新：

```text
frontend/src/router/index.ts
frontend/src/main.ts
frontend/src/components/StudioShell.vue
frontend/src/views/ProjectWorkspace.vue
```

Route：

```text
/projects/:projectId/shot-workbench
```

### 三栏工作台

左栏：

```text
Final Shot 列表
缩略图
镜头号
Source 起点
时长
播放当前 Shot 自动高亮
点击 Shot 直接 seek
```

中栏：

```text
F03 Proxy 播放器
当前 Shot 起止
Shot Timeline
首 / 25% / 50% / 75% / 尾关键帧
点击关键帧 seek
```

右栏：

```text
Final Start / End
公共边界保存
播放点拆分（新增镜头）
与前一镜合并
与后一镜合并
Auto Evidence 来源
确认 Final Shots
```

人物 / 场景 / 景别 / 运镜 / 动作 / 对白目前只占位，没有伪造结果。

### 时间映射

浏览器 currentTime / FFmpeg -ss 使用媒体相对时间：

```text
relative_seconds = (source_us - edit_set.source_start_us) / 1e6
```

Source absolute timestamp 不直接写入播放器 currentTime。

---

# Tests

新增：

```text
engine/tests/unit/test_database_migration_f05.py
engine/tests/unit/test_shot_workbench_f05.py
```

同时修正：

```text
engine/tests/unit/test_database_migration_f04.py
```

原因：F04 原测试错误地永久断言 Alembic head=0005；新增 F05 后 head 必然推进。现在 F04 只检查自己的结构，F05 测试负责断言当前 head=0006。

---

# 当前工具环境限制

尝试从当前 ChatGPT 命令容器 clone GitHub 时 DNS 失败：

```text
Could not resolve host: github.com
```

因此本轮不能声称已经在工具容器执行：

```text
pytest
npm run typecheck
npm run build
```

代码已经写入 main，但最终编译/运行必须由用户 Windows 本机验收。

---

# 用户本机下一步

先拉代码：

```powershell
cd D:\ai-drama-studio
git pull
```

如果当前项目还要完成 F04 GPU 验收：

```text
先重启 8080 后端
→ 04 自动拉片
→ 重新自动拉片
→ 确认页面 device=cuda / torch=2.5.1+cu124
```

然后再第一次进入 F05。

自动测试：

```powershell
python -m pytest engine/tests -q

cd frontend
npm ci
npm run typecheck
npm run build
```

真实 F05 验收：

```text
05 镜头修正
→ 应自动初始化 31 个 Final Shot
→ 左侧缩略图正常
→ 视频正常播放
→ 点击 #Shot 能跳转
→ 播放时当前 Shot 跟随高亮
→ 调整一个边界并保存
→ 在播放点拆分
→ 再合并回来
→ 刷新页面结果仍存在
→ 最后确认 Final Shots
→ confirmed 后所有编辑按钮锁定
```

## 当前状态

```text
F01 STABLE / FROZEN
F02 STABLE / FROZEN
F03 STABLE / FROZEN
F04 READY_FOR_REVIEW / NOT FROZEN
F05 IN DEVELOPMENT / READY FOR LOCAL TEST
```
