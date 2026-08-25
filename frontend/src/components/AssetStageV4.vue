<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Episode, F05ModelStatus } from '../types/studio'
import AssetReviewMatrixV4 from './AssetReviewMatrixV4.vue'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

const status = ref<F05ModelStatus | null>(null)
const loading = ref(true)
const preparing = ref(false)
const error = ref('')

const missingModels = computed(() => (status.value?.models ?? []).filter((item) => !item.ready))

/**
 * 职责：只读取人物 V4 固定模型状态，不触发联网。
 * 输入：无；输出：YuNet / SFace / YOLOX / YoutuReID 准备状态。
 * 为什么：正式资产 Run 不能在后台静默下载模型，用户必须明确知道当前人物能力是否完整。
 */
async function refreshModelStatus(): Promise<void> {
  try {
    status.value = await api.getF05ModelStatus()
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物模型状态读取失败'
  } finally {
    loading.value = false
  }
}

/**
 * 职责：用户显式准备人物 V4 所需全部固定模型。
 * 输入：点击动作；输出：更新后的模型状态。
 * 为什么：YOLOX / YoutuReID 权重较大，必须由用户明确触发，而不是资产分析时偷偷联网。
 */
async function prepareModels(): Promise<void> {
  preparing.value = true
  error.value = ''
  try {
    status.value = await api.prepareF05Models()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物 V4 模型准备失败'
  } finally {
    preparing.value = false
  }
}

onMounted(refreshModelStatus)
</script>

<template>
  <div class="asset-stage-v4">
    <div v-if="!loading && status && !status.ready" class="character-v4-banner warning">
      <div>
        <strong>人物识别 V4 模型未准备完整</strong>
        <span>新人物链需要 YOLOX Person Detection + YuNet/SFace + YoutuReID。模型未准备前不要重新提取资产，旧 Current 会继续保留。</span>
        <small v-if="missingModels.length">缺少：{{ missingModels.map((item) => item.filename).join('、') }}</small>
      </div>
      <button :disabled="preparing" @click="prepareModels">{{ preparing ? '正在准备模型…' : '准备人物 V4 模型' }}</button>
    </div>

    <div v-else-if="!loading && status?.ready" class="character-v4-banner ready">
      <div>
        <strong>人物识别 V4 · READY</strong>
        <span>YOLOX Person + YuNet/SFace + YoutuReID 已就绪；重新提取资产后会使用新人物 Evidence。</span>
      </div>
    </div>

    <div v-if="error" class="character-v4-error">{{ error }}</div>
    <AssetReviewMatrixV4 :project-id="props.projectId" :episodes="props.episodes" />
  </div>
</template>

<style scoped>
.asset-stage-v4{min-height:100%}.character-v4-banner{margin:14px 22px 0;padding:10px 13px;border:1px solid;border-radius:11px;display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:12px}.character-v4-banner>div{min-width:0;display:grid;gap:2px}.character-v4-banner strong{font-size:13px}.character-v4-banner span,.character-v4-banner small{line-height:1.45}.character-v4-banner.warning{background:#fff9eb;border-color:#f1d58d;color:#73510b}.character-v4-banner.warning span,.character-v4-banner.warning small{color:#8b6a25}.character-v4-banner.ready{background:#effbf5;border-color:#bfe7d2;color:#176a45}.character-v4-banner.ready span{color:#49806a}.character-v4-banner button{flex:0 0 auto;border:0;border-radius:8px;padding:8px 12px;background:#2f60e8;color:#fff;font-weight:750;cursor:pointer}.character-v4-banner button:disabled{opacity:.6;cursor:wait}.character-v4-error{margin:8px 22px 0;padding:8px 11px;border-radius:8px;background:#fff0f0;color:#b53a3a;font-size:12px}
</style>
