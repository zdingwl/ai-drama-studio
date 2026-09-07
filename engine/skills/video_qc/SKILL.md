# Video QC Skill

- **Skill ID:** `video_qc`
- **Version:** `1.0.0`
- **Status:** `CONTRACT_ONLY`
- **Runtime Model / Provider:** independent video/VLM QC provider explicitly configured for generated-segment evaluation

## Purpose

对 H3 或其他生成 Provider 的结果进行**独立语义/结构质检**，判断生成视频是否真正满足目标分镜和连续性要求，并给出可执行的重试纠正信息。

## Inputs

- 当前 GenerationSegment revision
- 当前 GenerationAttempt / generated video asset
- 当前 storyboard segment contract
- TargetCharacter / TargetScene / TargetProp refs
- 目标动作、表演、镜头、continuity handoff
- 需要承载的 TargetDialogue / measured TTS duration（如适用）
- 可比较的 Reference Clip / reference anchors（如适用）

## Rules

1. QC 与生成 Prompt 分离；不得因为是同一模型家族就默认生成结果正确。
2. 至少检查：
   - character identity / count；
   - clothing / appearance consistency；
   - scene / important props；
   - action order；
   - expression / performance；
   - camera / framing / composition / motion；
   - start state / end state；
   - continuity handoff；
   - duration suitability；
   - dialogue/lipsync prerequisites。
3. 每个检查项输出 PASS / FAIL / UNKNOWN 和 evidence/说明。
4. `RETRY` 必须给出针对本次失败原因的纠正指令，不得无差别重复相同 Prompt。
5. `BLOCK` 只用于输入本身缺失/冲突或无法安全自动继续的内容问题。
6. H3/模型离线、CUDA OOM、文件损坏、下载失败等属于 runtime failure，不得由 QC 伪装成内容 BLOCK。
7. 对审美主观项可以给 confidence，但人物错、数量错、场景错、关键动作缺失、连续性断裂等硬约束优先。
8. QC 不修改锁定剧本、TargetCharacter、TargetScene 或 TargetDialogue。

## Forbidden Behaviors

- 看到画面“差不多”就忽略关键人物/动作/道具错误。
- 为让结果 PASS 而修改验收标准或 storyboard。
- 在 QC 阶段重新创作剧情或对白。
- 把 runtime failure 创建成人工内容 review case。
- 没有 evidence/失败原因就输出 RETRY。
- 把旧 GenerationSegment revision 的 PASS 复用到新 revision。

## Output Contract

```json
{
  "generation_segment_revision": "...",
  "generation_attempt_revision": "...",
  "skill": {"id": "video_qc", "version": "1.0.0"},
  "checks": [
    {
      "name": "character_identity",
      "status": "PASS",
      "evidence": [],
      "detail": "..."
    }
  ],
  "decision": "PASS",
  "failure_reasons": [],
  "retry_corrections": [],
  "unknowns": []
}
```

`decision` 只允许 `PASS` / `RETRY` / `BLOCK`。运行时错误由调用层记录，不进入这三个内容决策值。

## Validator

- segment/attempt revision 必须是当前要验收的版本。
- 硬约束 FAIL 时总 decision 不得为 PASS。
- RETRY 至少包含一条 failure reason 和对应 correction。
- BLOCK 必须明确指出缺失/冲突的上游正式输入。
- PASS 必须覆盖配置要求的全部 hard checks。
- QC 输出不得产生新的 TargetDialogue、TargetCharacter 或 screenplay revision。

## Completion Criteria

- 每个生成段都有明确且可追溯的 PASS/RETRY/BLOCK 结论；
- 失败能定位到人物、场景、动作、表演、镜头、连续性或时长等具体原因；
- RETRY 能形成针对性的下一次生成修正；
- 只有通过 QC 的当前 revision 才能进入后续口型/音频/字幕/拼接链。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
