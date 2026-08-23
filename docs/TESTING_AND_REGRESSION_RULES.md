# AI Drama Studio — Testing & Regression Rules

## 1. 目的

逐 Feature 开发的前提是：后续 Feature 不能把已经 Stable 的上游功能悄悄破坏。

因此测试分为两类：

```text
Current Feature Test
+
Affected Stable Feature Regression Test
```

只有两者都通过，当前 Feature 才能进入 `READY_FOR_REVIEW`。

---

## 2. 测试层级

推荐目录：

```text
tests/
├── unit/
├── integration/
├── regression/
└── fixtures/
```

### Unit

验证纯函数、Schema、转换、状态机、时间换算、错误映射等。

### Integration

验证 API + DB + File / Provider Adapter / FFmpeg 等跨层协作。

### Regression

保护已经 STABLE/FROZEN 的业务 Contract。

---

## 3. 固定媒体 Fixture

真实短剧验收不能完全替代自动回归。

应逐步建立短小、可提交或可稳定下载/生成的 Fixture，例如：

```text
hardcut_10s.mp4
short_dialogue.mp4
vfr_sample.mp4
no_audio.mp4
ntsc_30000_1001.mp4
stereo_audio_sample.mp4
```

Fixture 必须记录：

- 目的；
- 时长；
- FPS / VFR；
- 音频；
- 预期结果；
- 来源/生成方法；
- 版权/使用说明（适用时）。

完整商业短剧原片不要直接提交 Git。

---

## 4. Stable Feature 必须形成 Regression Baseline

Feature 用户验收通过后，至少将关键 Contract 行为加入 regression。

例如 F04 Shot Detection Stable 后：

- 输入固定 proxy；
- 输出结构符合 Shot Contract；
- 时间字段单位正确；
- 不覆盖人工 Final 字段；
- 失败路径正确。

不要求 AI 模型的概率输出逐帧完全一致，但 Contract、边界条件和可接受阈值必须可验证。

---

## 5. 修改共享代码时如何决定回归范围

当前 Feature 文档必须写：

```text
Affected Stable Features:
- Fxx
- Fyy
```

以下修改默认需要扩大回归范围：

- database base / repository；
- media/timebase；
- FFmpeg wrapper；
- task/job state；
- Provider base adapter；
- shared DTO/Schema；
- workspace path utility；
- file transaction/recovery；
- dependency/invalidation engine。

禁止只运行当前 Feature 测试就宣称完成。

---

## 6. AI / Provider 测试

外部付费 Provider 不应该在普通单元测试中反复真实计费。

需要：

- Adapter 单元测试使用 mock/fake；
- 测试 timeout / unknown / retry / resume；
- 真实 Provider 验收使用明确标记的 integration/manual test；
- 记录真实调用日期、模型版本、成本（能获取时）。

---

## 7. 媒体时间回归

涉及时间轴的共享代码至少覆盖：

- 24 fps；
- 25 fps；
- 24000/1001；
- 30000/1001；
- VFR；
- source start_time 非 0；
- 44.1k / 48k audio；
- Source→Proxy→Source round trip。

---

## 8. DB / Migration 回归

Migration Feature 必须测试：

```text
old schema / old project
→ backup
→ migrate
→ reopen
→ verify data
```

可 downgrade 时也要验证 downgrade；不能安全 downgrade 时必须明确说明。

---

## 9. 用户验收与自动测试的边界

自动测试 PASS 不等于 Feature Stable。

流程：

```text
自动/回归/真实素材测试通过
→ READY_FOR_REVIEW
→ 用户按验收步骤实际操作
→ 用户明确确认
→ STABLE/FROZEN
```

---

## 10. Feature 文档必须记录

至少：

```text
Current Feature Tests
Regression Scope
Regression Results
Real Sample Test
Known Limitations
```

如果出现失败但用户接受为 V1 Limit，必须在 Feature 文档中明确记录，不能当作“测试通过”隐藏。

---

## 11. Stable Gate

```text
[ ] 当前 Feature unit/integration 测试通过
[ ] Affected Stable Features 已识别
[ ] 受影响 regression 全部通过
[ ] 真实短剧/媒体样本测试完成
[ ] 测试环境/版本已记录
[ ] 已知限制已记录
[ ] Agent 仅标记 READY_FOR_REVIEW
[ ] 用户验收后才 STABLE/FROZEN
```
