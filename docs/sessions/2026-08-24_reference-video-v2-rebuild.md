# 2026-08-24 — Reference Video V2 Rebuild

## 用户最终决策

用户明确要求：

> 按新的 Reference Video 规划重新修改项目，不用受原有程序限制，原内容可以完全删除。

因此本次不做 Legacy Contract 兼容性设计。

## 本次完成

### Backend

新增：
- `engine/app/studio_v2.py`
- `engine/app/media_v2.py`

替换：
- `engine/app/main.py`

V2 已实现：
- Project CRUD 基础；
- Project 多 Episode；
- Episode 多文件导入；
- Episode 拖动排序对应的后端 reorder；
- 单 Episode F03 预处理；
- Project 顺序批量预处理；
- 单 Episode F04 自动拉片；
- Project 顺序批量拉片；
- Shot Reference Clip；
- Shot Thumbnail；
- Reference/Thumbnail HTTP 读取。

V2 Schema 已预留：
- Character；
- Scene；
- Prop；
- Dialogue；
- Asset；
- Voice；
- Generation。

### Frontend

新增：
- `frontend/src/views/ProjectList.vue`
- `frontend/src/views/ProjectStudio.vue`
- `frontend/src/api/client.ts`
- `frontend/src/types/studio.ts`

替换：
- `frontend/src/App.vue`
- `frontend/src/main.ts`
- `frontend/src/router/index.ts`
- `frontend/src/styles.css`
- `frontend/vite.config.ts`

UI 固定为 F01-F13 生产链。

F01-F04 真实可操作；F05-F13 明确显示待开发，不复用旧页面假装完成。

### Tests

新增：
- `engine/tests/v2/test_studio_v2.py`
- `engine/tests/v2/test_media_v2.py`

`pyproject.toml` 默认测试入口改为 `engine/tests/v2`。

### Docs

重写：
- `AGENTS.md`
- `SKILL.md`
- `README.md`
- `docs/PROJECT_STATE.md`

新增：
- `docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md`

## 架构核心

```text
原 Shot Reference Video
负责：动作 / 构图 / 镜头运动 / 大部分空间关系 / 节奏

结构化数据
负责：Character / Scene / Key Prop / Dialogue / Speaker / Track / Mask / Replacement Assets / Voice
```

以后 F05 的开发优先级：

```text
1. Character Identity
2. Character Track
3. Dialogue / ASR
4. Speaker → Character
5. Character Mask
6. Scene ID
7. Key Prop ID
8. Dialogue Type / Emotion / Style
9. Short Description
```

不优先做复杂动作和摄影参数的文字结构化。

## 当前分支

```text
rebuild/reference-video-v2
```

未创建 PR，未合并 main。

## 下一步验收

在用户 Windows 本机：

1. `pip install -r engine/requirements.txt`
2. 确认 `ffmpeg` / `ffprobe`
3. 启动 FastAPI + Vue
4. 创建新 V2 项目
5. 一次导入多集
6. 拖动排序
7. 顺序批量预处理
8. 顺序批量拉片
9. 检查 Shot 边界、Reference Clip、Thumbnail
10. 验收 F01-F04 后进入 F05
