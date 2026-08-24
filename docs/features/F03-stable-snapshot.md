# F03 — 视频预处理 Stable / Frozen Snapshot

Feature ID: F03  
Status: STABLE / FROZEN  
User Acceptance: PASSED  
Official Baseline: main  
Accepted At: 2026-08-24 12:25 +08:00

> 本文件是 F03 用户实际验收后的冻结快照。后续 Feature 可以兼容性扩展 F03 输出，但不得静默改变本文件中的 F03 对外 Contract。

## 1. 用户验收结论

用户在 Windows 本机完成真实项目复测，并明确确认：

```text
测试通过
```

实际验收过程中曾发现并修复：

```text
旧 processing 残留导致无法重试
旧版 0003 Audio CHECK 导致有音频 Source 创建 processing 失败
```

最终通过正式 0004 Compatibility Migration 和 processing 安全重试逻辑修复后，真实项目页面已经显示：

```text
PREPROCESS READY
proxy.mp4      ready
audio.wav      ready
thumbnail.jpg  ready
Timeline Mapping persisted
```

应用重启后仍可读取同一份 F03 结果。

因此：

```text
F03 = STABLE / FROZEN
```

F04 尚未开始。

---

## 2. 冻结业务能力

F03 固定负责：

```text
读取 F02 ready Source Video
→ 开始前重新核验 Source size + SHA-256
→ 建立 source_preprocess processing 恢复锚点
→ staging 生成 proxy.mp4
→ Source 有音频时生成 audio.wav
→ 生成 thumbnail.jpg
→ FFprobe / size / SHA / Profile 校验
→ 保存 Source↔Proxy / Audio Timeline Mapping
→ publish 前再次核验 Source 未在处理中变化
→ staging 发布为 final
→ source_preprocess = ready
→ 页面展示派生资产与映射
→ 重启后仍可读取
```

F03 不负责：

```text
Shot Detection / 自动拉片
Shot 人工修正
ASR
人物识别
Speaker 匹配
Scene
翻译
AI 生成
最终合成
```

这些不得在 F03 回归修复中偷偷加入。

---

## 3. Workspace Contract

F02 冻结原片继续保持只读：

```text
<workspace>/source/SOURCE_<UUID>/original.<ext>
```

F03 正式派生资产固定：

```text
<workspace>/preprocess/SOURCE_<UUID>/
├── proxy.mp4
├── audio.wav       # 仅 Source 有音频时存在
└── thumbnail.jpg
```

处理中固定使用：

```text
<workspace>/preprocess/.staging/SOURCE_<UUID>/
```

冻结规则：

- F03 绝不覆盖、移动或删除 F02 `original.<ext>`；
- DB 保存相对 Workspace 路径；
- 派生资产全部 staging 生成并校验后才发布 final；
- Recovery/cleanup 只删除系统明确拥有的 F03 文件；
- 出现未知文件时保留现场，不递归删除。

---

## 4. Database / Migration Contract

F03 数据表：

```text
source_preprocess
```

相关 Migration：

```text
0003_create_source_preprocess
0004_repair_source_preprocess_audio_constraint
```

0004 属于 F03 正式冻结基线，不得删除或通过改写已执行的 0003 来替代。

状态固定：

```text
processing
ready
```

核心字段语义固定包含：

```text
source_video_id
project_id
status
profile_version
source_sha256_snapshot
proxy_relative_path
proxy_file_size_bytes
proxy_sha256
proxy_duration_us
proxy_video_time_base_num
proxy_video_time_base_den
proxy_fps_num
proxy_fps_den
proxy_to_source_offset_us
audio_relative_path
audio_file_size_bytes
audio_sha256
audio_duration_us
audio_sample_rate
audio_channels
audio_to_source_offset_us
thumbnail_relative_path
thumbnail_file_size_bytes
thumbnail_sha256
thumbnail_source_time_us
source_video_time_base_num
source_video_time_base_den
created_at
completed_at
```

冻结约束：

```text
processing：
- 已知目标路径可以先保存；
- 尚未生成的媒体 metadata 可以 NULL；
- 有音频 Source 可以先保存 audio_relative_path，不能要求 WAV metadata 此时已完整。

ready：
- Proxy + Thumbnail + Timeline Mapping 必须完整；
- 有 Audio 时 path/size/hash/duration/sample_rate/channels/offset 必须完整；
- F03 V1 Audio 固定 16000 Hz / mono。
```

已有数据库 revision 落后于代码 head 时，继续使用共享 SQLite `Connection.backup()` Gate 后再 Alembic upgrade。

---

## 5. Proxy Profile V1

冻结参数：

```text
文件名：proxy.mp4
视频：H.264 / libx264
CRF：23
preset：fast
pixel format：yuv420p
最大宽高：1280 × 720
保持原始比例
禁止放大小视频
-fps_mode passthrough
不强制 VFR → CFR
Source 有音频时：AAC 128k
-movflags +faststart
```

后续若需要不同 Proxy Profile，必须新增 profile_version / V2，不得静默改变 F03 V1 已冻结结果含义。

---

## 6. Analysis Audio Contract

Source 有主音频流时生成：

```text
audio.wav
PCM s16le
16000 Hz
mono
```

用途：

```text
F08 ASR
F09 Speaker / Character 匹配等分析
```

它不是最终混音母带。

Source 无音频时：

```text
不生成 audio.wav
不伪造静音音轨
Audio DB 字段为空
```

---

## 7. Thumbnail Contract

固定文件：

```text
thumbnail.jpg
```

固定选取规则：

```text
proxy_time_us = min(proxy_duration_us / 10, 5_000_000us)
```

DB 保存的是映射后的 Source Domain 时间：

```text
thumbnail_source_time_us
```

Thumbnail 只是 F03 分析/展示派生资产，不是 Shot 缩略图集合；F04 不得把这一张图片当成 Shot Detection 结果。

---

## 8. Time / Timeline Mapping Contract

F03 继续遵守全局媒体时间规则：

```text
权威时间 = integer microseconds
```

公共换算能力位于：

```text
engine/app/core/media_time.py
```

冻结映射：

```text
source_us = proxy_us + proxy_to_source_offset_us
source_us = audio_us + audio_to_source_offset_us
```

Offset 必须来自实际媒体 timestamp，不允许假设：

```text
Proxy 0 == Source 0
Audio 0 == Source 0
```

VFR：

- Proxy 不强制 CFR；
- 下游 F04 不得把 `frame_index / fps` 当成唯一 Source Timeline 定位方法；
- 下游必须使用 timestamp + F03 mapping。

媒体时长读取语义冻结为：

```text
selected stream.duration
→ 缺失时才回退 format.duration
```

---

## 9. Source Integrity Contract

开始预处理前：

```text
磁盘 Source file_size + SHA-256
== F02 source_videos 记录
```

FFmpeg / inspect 完成、正式 publish 前：

```text
再次计算磁盘 Source size/hash
== F02 source_videos size/hash
== 本次 source_sha256_snapshot
```

若 Source 在处理中被系统外替换：

```text
SOURCE_VIDEO_INTEGRITY_MISMATCH
→ 不发布 final
→ 清理本次明确拥有的 staging
→ 删除本次 processing row
→ 不修改或删除 F02 Source
```

---

## 10. Processing / Recovery Contract

正常失败边界：

```text
final 发布前失败
→ 只清理本次系统已知 F03 staging
→ 删除本次 processing row

final 已发布但 DB ready finalization 失败
→ 不删除 final 派生资产
→ 保留 processing
→ 下次 Recovery 恢复 ready
```

用户重试时的冻结规则：

```text
已有 ready
→ PREPROCESS_ALREADY_EXISTS
→ 禁止重复预处理

已有 processing + 完整合法 final
→ 自动恢复 ready

已有 processing + staging 最近 30 秒仍有活动
→ PREPROCESS_IN_PROGRESS
→ 不删除，避免误伤正在运行的 FFmpeg

已有 processing + staging 已停止写入且只有系统已知文件
→ 安全清理 staging + processing
→ 允许本次重新处理

已有 processing + 无 staging/final 且记录超过保护窗口
→ 删除旧 processing
→ 允许本次重新处理

未知文件 / 异常 final / Source Hash 不一致
→ PREPROCESS_RECOVERY_REQUIRED
→ 保留现场
```

任何 Recovery 路径均不得删除 F02 Source。

---

## 11. API Contract

F03 API 固定为：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

GET：

```text
无 ready 结果 → 200 null
ready → 200 SourcePreprocessDTO
```

POST：

```text
成功完成 → 201 SourcePreprocessDTO
```

稳定错误至少包括：

```text
PREPROCESS_SOURCE_REQUIRED
PREPROCESS_ALREADY_EXISTS
PREPROCESS_IN_PROGRESS
PREPROCESS_RECOVERY_REQUIRED
SOURCE_VIDEO_INTEGRITY_MISMATCH
PREPROCESS_FFMPEG_UNAVAILABLE
PREPROCESS_FFPROBE_UNAVAILABLE
PREPROCESS_GENERATION_FAILED
PREPROCESS_PROCESSING_FAILED
PREPROCESS_VALIDATION_FAILED
PREPROCESS_FINALIZATION_PENDING
PREPROCESS_FILE_MISSING
```

Controller 继续遵守：

```text
HTTP → Business → Response
```

Controller 不直接 SQL、FFmpeg、FFprobe、Hash、文件发布或 Recovery。

---

## 12. Core Function Contract

F03 冻结核心函数保持 7 个：

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

Controller 保持 2 个：

```text
get_source_preprocess_api()
preprocess_source_video_api()
```

详细职责继续参考：

```text
docs/features/F03-function-contracts.md
```

内部 helper 可以重构，但不得改变本快照冻结的业务语义、安全边界和时间语义。

---

## 13. Frontend Contract

正式路由：

```text
/projects/:projectId/preprocess
```

冻结交互：

```text
无 Source
→ 阻止处理并引导 F02

Source ready / 未处理
→ 展示 Source 信息
→ 展示固定 Profile V1
→ “开始视频预处理”

processing
→ 显示真实处理中状态
→ 不伪造百分比

ready
→ 显示 PREPROCESS READY
→ Proxy / Audio / Thumbnail
→ 文件大小 / 时长 / FPS / Time Base
→ Analysis Audio 16000Hz / mono
→ Thumbnail Source 时间
→ Source SHA Snapshot
→ Proxy→Source / Audio→Source offset
→ 结果锁定，不提供重复预处理入口
```

沿用 F01/F02 已冻结的深色 StudioShell 与桌面可读字号。

F04「自动拉片」在 F03 冻结时仍未开发，不得由 F03 页面提前生成 Shot。

---

## 14. Accepted Verification Baseline

开发阶段已经完成：

```text
Media Time targeted tests
0003 Migration / Constraint tests
0002 → backup → F03 migration tests
真实 1920×1080 + Audio FFmpeg 链路
真实 No-Audio FFmpeg 链路
非零 Source start_time Mapping
Synthetic VFR cadence 验证
processing / ready DB constraint 验证
0004 compatibility migration 机制验证
processing 安全重试相关自动测试编写
Source 处理中二次 SHA 防护测试编写
stream.duration 语义测试编写
```

用户在 Windows 真实项目验收中最终确认：

```text
Proxy 已生成
Analysis Audio 已生成
Thumbnail 已生成
Timeline Mapping 已显示并持久化
0004 已解决旧 0003 Audio CHECK 的 409
重启后 F03 ready 仍可读取
```

随后用户于 2026-08-24 12:25 +08:00 明确回复：

```text
测试通过
```

因此 User Acceptance Gate = PASS。

---

## 15. Frozen Change Rule

以下 F03 行为以后不能直接改：

```text
F03 只从 F02 Source 派生、不修改原片
preprocess/SOURCE_xxx/ 正式目录规则
Proxy Profile V1 语义
Analysis Audio 16kHz / mono / PCM16 语义
无音频不伪造 WAV
Thumbnail 选取规则
integer microseconds
Proxy/Audio → Source offset 语义
VFR 不强制 CFR
Source 开始前 + publish 前双重完整性检查
processing / ready 状态语义
processing 安全重试与未知文件保护
0003 + 0004 Migration 历史
2 个 F03 API 既有语义
7 个核心函数的业务职责边界
```

若未来必须改变：

```text
Change Request
→ 影响分析
→ 数据迁移 / Profile V2 / Contract V2
→ 用户明确批准
→ 实现
→ F01 + F02 + F03 回归
```

F04 及以后可以读取和引用 F03 派生资产，但不得静默重新解释或覆盖 F03 已冻结的 Source Domain 时间和文件身份。
