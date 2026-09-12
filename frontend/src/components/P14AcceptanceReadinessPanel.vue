<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError, apiRequest } from '@/lib/api'

interface P14AcceptanceReadiness {
  project_id: string
  technical_ready: boolean
  target_audio_artifact_id: string | null
  target_audio_revision: number | null
  timing_plan_artifact_id: string | null
  timing_plan_revision: number | null
  clip_count: number
  timing_item_count: number
  provider_job_count: number
  provider_jobs_succeeded: number
  media_verified_count: number
  duration_verified_count: number
  blockers: string[]
  manual_checks_required: string[]
}

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const checking = ref(false)
const error = ref('')
const result = ref<P14AcceptanceReadiness | null>(null)

async function runCheck() {
  if (!projectId.value) return
  checking.value = true
  error.value = ''
  try {
    result.value = await apiRequest<P14AcceptanceReadiness>(
      `/projects/${projectId.value}/p14/acceptance-readiness`,
      { cache: 'no-store' },
    )
  } catch (exc) {
    if (
      exc instanceof ApiError
      && exc.status === 404
      && exc.code === 'HTTP_ERROR'
      && exc.message === 'Not Found'
    ) {
      error.value = '当前页面代码已更新，但 8000 后端仍是旧版本。请退出旧的 Studio / backend 进程并重新运行 start.cmd（Linux / WSL 使用 ./start.sh），然后刷新页面。'
    } else {
      error.value = exc instanceof Error ? exc.message : 'P14 技术验收检查失败'
    }
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <section class="p14-readiness">
    <header>
      <div>
        <p class="eyebrow">P14 · 验收准备</p>
        <h2>技术验收就绪检查</h2>
      </div>
      <button type="button" :disabled="checking" @click="runCheck">
        {{ checking ? '正在重新校验…' : '运行技术验收检查' }}
      </button>
    </header>

    <p class="guidance">
      该检查只验证正式 Artifact、ProviderJob、真实 WAV、SHA256、重新 ffprobe 的实际时长与 Timing 是否自洽。
      它不会代替人工听审，也不会自动产生 P14 PASS 或把 TTS / TIMING 升级为 AVAILABLE。
    </p>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="result">
      <div class="status" :class="{ ready: result.technical_ready, blocked: !result.technical_ready }">
        <strong>{{ result.technical_ready ? '技术链路已就绪，可进入最终人工验收' : '技术链路仍有阻塞项' }}</strong>
        <span>TARGET_AUDIO r{{ result.target_audio_revision ?? '-' }} · TIMING_PLAN r{{ result.timing_plan_revision ?? '-' }}</span>
      </div>

      <div class="metrics">
        <div><strong>{{ result.clip_count }}</strong><span>正式对白</span></div>
        <div><strong>{{ result.provider_jobs_succeeded }} / {{ result.provider_job_count }}</strong><span>ProviderJob 成功</span></div>
        <div><strong>{{ result.media_verified_count }} / {{ result.clip_count }}</strong><span>媒体 SHA 通过</span></div>
        <div><strong>{{ result.duration_verified_count }} / {{ result.clip_count }}</strong><span>ffprobe 时长一致</span></div>
        <div><strong>{{ result.timing_item_count }} / {{ result.clip_count }}</strong><span>Timing 覆盖</span></div>
      </div>

      <div v-if="result.blockers.length" class="blockers">
        <strong>必须先解决</strong>
        <ul>
          <li v-for="item in result.blockers" :key="item">{{ item }}</li>
        </ul>
      </div>

      <div class="manual">
        <strong>仍必须人工完成</strong>
        <ol>
          <li v-for="item in result.manual_checks_required" :key="item">{{ item }}</li>
        </ol>
      </div>
    </template>

    <p v-else class="muted">
      在你准备做最终 P14 验收时再运行。检查会读取当前正式音频并逐句重新执行媒体完整性和 ffprobe 校验。
    </p>
  </section>
</template>

<style scoped>
.p14-readiness{margin:24px 0;padding:24px;border:1px solid var(--border-color,#ddd);border-radius:16px}.p14-readiness header{display:flex;justify-content:space-between;gap:16px;align-items:center}.eyebrow{margin:0;font-size:12px;opacity:.65}.guidance{padding:10px 12px;border-left:3px solid rgba(47,84,235,.45);background:rgba(47,84,235,.05)}.error,.blocked{color:#b42318}.status{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;padding:12px;margin-top:14px;border-radius:10px;background:rgba(127,127,127,.06)}.ready{color:#067647}.metrics{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:10px;margin:14px 0}.metrics>div{display:grid;gap:3px;padding:12px;border:1px solid rgba(127,127,127,.18);border-radius:10px}.metrics strong{font-size:18px}.metrics span{font-size:12px;opacity:.65}.blockers,.manual{padding:14px;border-radius:10px;margin-top:12px}.blockers{background:rgba(180,35,24,.06);border:1px solid rgba(180,35,24,.18)}.manual{background:rgba(127,127,127,.05);border:1px solid rgba(127,127,127,.18)}.blockers ul,.manual ol{margin:8px 0 0;padding-left:22px}.muted{opacity:.7}@media(max-width:850px){.metrics{grid-template-columns:repeat(2,minmax(130px,1fr))}.p14-readiness header{align-items:flex-start;flex-direction:column}}
</style>
