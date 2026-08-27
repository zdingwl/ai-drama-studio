# AI Drama Studio — Reference Video V2

本项目是 Windows 本地使用的 AI 短剧本地化重制工作台。

> **新对话 / 新开发者先读：**
> `AGENTS.md` → `SKILL.md` → `docs/PROJECT_STATE.md` → `docs/CURRENT_IMPLEMENTATION_MANIFEST.md`
>
> **Windows 首次安装 / Runtime / 前后端启动 / 更新 / 故障排查：**
> `docs/INSTALL_AND_RUN_WINDOWS.md`

当前架构不把“拉片”理解为生成一份尽可能详细的文字报告，而是把原视频拆成独立 Shot，并保存每个 Shot 的 **Reference Video**。后续人物、场景、关键道具、目标语言对白和声音作为控制条件参与重制。

## 当前实现

```text
01 剧集管理                         ✅ IMPLEMENTED
02 拉片 / Reference Clip             ✅ IMPLEMENTED，真实 Windows 视频仍是 Release Gate
03 资产                              ✅ Character V10.1 已实现，最新 Shot Binding 修复待真实视频复验
04 内容剧本                           ⏳ PLANNED / 部分底层兼容代码存在
05 重制设计                           ⏳ PLANNED
06 生成 / 导出                        ⏳ PLANNED
```

当前人物正式基线：

```text
Character V10.1
runtime:  character-v10.1-capture-first-model-classification
asset:    f05-assets-v10.1-person-evidence-model-classification
resolver: person-evidence-model-classifier-v10.1
```

完整当前状态：`docs/PROJECT_STATE.md`  
实现清单：`docs/CURRENT_IMPLEMENTATION_MANIFEST.md`  
人物 V10.1：`docs/ASSET_CHARACTER_RECOGNITION_V10_1.md`

## 核心流程

```text
项目
→ 多个 Episode
→ 顺序预处理
→ 顺序自动拉片
→ Shot + Reference Clip
→ 人物 / Scene / Key Prop / Dialogue
→ Final Asset / Binding
→ 替换资产 / Voice / 本地化
→ 按 Shot 规划重制策略
→ Reference Video 视频重制
→ 弹性 Production Timeline
→ QC / Export
```

批量处理始终按 `Episode.sort_order` 一集一集执行，不并行跑多个剧集。

## 当前人物技术链

```text
Reference Clip
→ YOLOX Person Detection
→ isolated Person Instance crops
→ capture-first Person Evidence
→ YoutuReID primary identity signal
   + clothing/body support
   + optional YuNet/SFace Face support
→ temporal MOT
→ Project-level identity classification
→ RESOLVED / UNRESOLVED
→ V10.1 unresolved Track → known identity recovery
→ Final Gate
→ Character + ShotCharacterBinding
```

关键原则：

- Track 不是 Character；
- Face 不是 V10.1 人物身份的必需条件；
- 新身份至少需要 3 个独立 Shot / 3 张可用 Person Evidence；
- 同一采样时刻不同人物 cannot-link；
- 强 Face 冲突阻断合并；
- Shot-level Track recovery 只能挂已有已确认 Character，不能创造新人；
- `UNRESOLVED` 不进入 Final Character。

## 当前拉片技术栈

Backend：
- Python / FastAPI / SQLAlchemy / SQLite
- FFmpeg / FFprobe
- 当前 Shot pipeline 以仓库正式 wiring 和 `PROJECT_STATE.md` 为准
- Source PTS / frame ownership
- Reference Clip

Frontend：
- Vue 3
- TypeScript
- Vue Router
- Vite

仓库中仍保留多个历史 Shot/Character 版本模块作为兼容或算法参考。不要根据文件名或旧 Feature 文档判断当前正式版本。

## 快速运行

完整首次安装请阅读 `docs/INSTALL_AND_RUN_WINDOWS.md`。

### 后端

```powershell
cd E:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

当前 FastAPI app version：

```text
2.4.1
```

### 前端

```powershell
cd E:\ai-drama-studio\frontend
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

## V2 本地数据

默认：

```text
data_v2/
├ studio_v2.sqlite3
├ models/
└ workspace/
```

可以设置：

```powershell
$env:AI_DRAMA_STUDIO_HOME="E:\ai-drama-studio-data"
```

模型 Runtime 和业务数据都不应提交到 Git。

## 当前用户操作

### 01 剧集管理

支持项目建立、多集导入、排序和删除/替换。

### 02 拉片

支持单集/顺序批量拉片，并保存 Shot Reference Clip、Thumbnail 与 Revision。

### 03 资产

当前重点是人物、场景、关键道具 Evidence 与 Final Binding。

人物 V10.1 已支持：

```text
Person Instance capture
multi-channel Person features
cross-Shot identity classification
risky-view strict confirmation
known-identity Track recovery
Final Character materialization
ShotCharacterBinding
```

**代码更新不会自动重算旧 Run。** 验证最新人物/绑定逻辑必须重新执行资产提取。

## 模型准备

人物当前固定模型集：

```text
YOLOX
YoutuReID
YuNet
SFace
```

模型准备/状态入口仍为：

```text
GET  /api/models/f05/status
POST /api/models/f05/prepare
```

V10.1 复用 V10 的模型文件，因此模型状态中看到 V10 model-package profile 不代表正式 runtime 已回退。

## 测试现实

V2 测试目录：

```powershell
python -m pytest engine/tests/v2 -q
```

当前整个 GitHub Actions **不是全绿**。已知失败类别包括轻量 CI 缺少完整 `cv2`/MOT/FFmpeg runtime、旧 V6 断言、部分 legacy workspace 预期以及 frontend `vue-tsc` / TypeScript compatibility。

因此仓库单元测试不能替代用户 Windows 本机真实短剧验收。

最新人物验收重点：

- Final Character 数量是否等于真实主要人物数量；
- 同框不同人是否保持 cannot-link；
- 侧身/背影/遮挡是否能正确归入已有身份；
- 人物资产识别正确时，Shot 是否也绑定到正确 Character；
- ambiguous Track 是否保持 unresolved 而不是误绑；
- 旧 Run 是否通过显式 rerun 才更新绑定。

## Legacy

仓库里保留旧业务代码、旧模型入口、旧 Feature/Frozen 文档和旧 Character V1–V10 资料用于历史参考。

正式当前事实以：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
当前可执行代码
```

为准。
