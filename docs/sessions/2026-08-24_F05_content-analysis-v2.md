# Session — 2026-08-24 — F05 Content Analysis V2

## 用户最新决定

继续 Reference Video V2，不回到旧程序结构。

本次正式推进：

```text
F05 智能内容识别 V1
```

## 已完成代码

新增：

```text
engine/app/content_models_v2.py
engine/app/character_visual_v2.py
engine/app/content_analysis_v2.py
engine/tests/v2/test_content_analysis_v2.py
frontend/src/f05.css
docs/F05_CONTENT_ANALYSIS_V2.md
```

修改：

```text
engine/app/main.py
engine/requirements.txt
frontend/src/types/studio.ts
frontend/src/api/client.ts
frontend/src/views/ProjectStudio.vue
frontend/src/main.ts
README.md
docs/PROJECT_STATE.md
```

## F05 人物视觉链

```text
Reference Clip
→ 18% / 50% / 82% 采样
→ YuNet Face Detection
+ OpenCV HOG Person Detection
→ SFace face embedding
+ body/clothing HSV histogram
→ Shot-local Track
→ Project-wide conservative candidate clustering
```

### 重要规则

- 人脸主证据，不等于人物只靠人脸；
- HOG 检测到但没脸的人也保留 body-only Track；
- body-only 不跨远距离 Shot 激进合并；
- 同一个 Shot 的两个 Track 禁止自动聚成同一 Candidate；
- F05 Candidate 不是 Final Character。

## Scene

当前使用 Thumbnail HSV visual clustering。

这是自动候选，不是最终语义命名。

## ASR

新增固定依赖：

```text
faster-whisper==1.2.1
```

默认：

```text
AI_DRAMA_WHISPER_MODEL=small
AI_DRAMA_WHISPER_DEVICE=auto
```

每 Episode 转写一次，再按 Source Timeline overlap 绑定 Shot。

## Speaker

当前可选。

如果设置：

```text
AI_DRAMA_DIARIZATION_MODEL_PATH
```

并安装兼容 pyannote.audio，则执行本地 Speaker Diarization。

否则：

```text
NOT_CONFIGURED
```

不会阻止其它组件。

## Speaker → Character

保守映射：
- 跨多个 Dialogue / Shot 统计 Speaker 与 Candidate 共现；
- 至少 2 条支持，且第一候选明显胜出才自动绑定；
- 单 Shot 唯一人物允许 0.50 低置信候选；
- 证据不足保持 unresolved。

## Key Prop

只完成正式 AI Evidence 数据结构：

```text
v2_prop_candidates
v2_shot_prop_evidence
```

暂不默认 Object Detector。

原因：通用检测到桌椅水杯 != 剧情关键道具。

后续应结合：

```text
Object Detection
+ Interaction
+ Repeated Appearance
+ Dialogue / Plot Context
```

## 新增 F05 数据表

```text
v2_content_analysis_runs
v2_character_candidates
v2_character_tracks
v2_scene_candidates
v2_shot_scene_evidence
v2_prop_candidates
v2_shot_prop_evidence
v2_speaker_segments
v2_analysis_dialogues
```

这些都是 AI Evidence。

Final 数据继续使用：

```text
v2_characters
v2_scenes
v2_props
v2_dialogues
```

由 F06 创建/维护。

## F05 API

```text
GET  /api/models/f05/status
POST /api/models/f05/prepare
POST /api/projects/{project_id}/content-analysis
GET  /api/projects/{project_id}/content-analysis/current
GET  /api/content-analysis/{run_id}
GET  /api/content-analysis/characters/{candidate_id}/cover
GET  /api/content-analysis/scenes/{candidate_id}/cover
```

## 前端

F05 已成为真实页面，不再显示待开发占位。

显示：
- 模型状态；
- 子组件状态；
- Character Candidate；
- Character Track 数；
- Scene Candidate；
- ASR Dialogue；
- Speaker / Mapping 状态；
- Prop 未配置状态。

## 仍需本机真实素材测试

```text
1. python -m engine.app.content_models_v2
2. F01-F04 准备真实多集短剧
3. 进入 F05 点击开始智能识别
4. 检查正脸 / 侧脸 / 背影 Track
5. 检查同人物跨 Shot 聚类
6. 检查同 Shot 多人物 cannot-link
7. 检查 Scene 是否过度聚类
8. 检查 Whisper 文本 / 时间
9. 检查 F05 重跑是否生成新 current Run
10. 检查前端页面
```

## 下一阶段

```text
F06 拉片审核与人工修正
```

F06 应直接围绕 F05 Current Run 的 AI Evidence 做：
- 人物命名 / 合并 / 拆分 / Shot 改绑；
- Scene 命名 / 合并 / Shot 改绑；
- Prop 增删 / 命名 / 合并；
- Dialogue 文本 / 类型 / Speaker 修正；
- 生成 Final Character / Scene / Prop / Source Dialogue。

不要重新引入旧 Candidate 页面和旧 Frozen Feature 逻辑。
