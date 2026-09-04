<script setup lang="ts">
import { ref } from 'vue'
import SourceCharacterAssetLibraryV1 from './SourceCharacterAssetLibraryV1.vue'
import TargetCharacterAssetPanelV1 from './TargetCharacterAssetPanelV1.vue'

const props = defineProps<{
  projectId: string
}>()

type CharacterAssetMode = 'source' | 'target'
const mode = ref<CharacterAssetMode>('source')
</script>

<template>
  <section class="character-asset-entry">
    <div class="character-asset-entry__intro">
      <div>
        <small>人物资产</small>
        <h2>分镜人物 → 正式人物资产 → 替换人物</h2>
        <p>
          分镜里识别到的人物只是证据。系统先跨分镜归并为项目级人物资产，再把人物资产绑定回所有出现的分镜；
          然后为正式人物设计新的本土化替换人物和可供 H3 使用的四视图。
        </p>
      </div>
      <div class="character-asset-entry__flow" aria-label="人物资产流程">
        <span>分镜人物</span><b>→</b><span>自动归并</span><b>→</b><span>分镜绑定</span><b>→</b><span>原片人物资产</span><b>→</b><span>替换人物 / 四视图</span>
      </div>
    </div>

    <nav class="character-asset-tabs" aria-label="人物资产类型">
      <button type="button" :class="{ active: mode === 'source' }" @click="mode = 'source'">
        <strong>原片人物</strong>
        <span>跨分镜归并、人物资产库、Shot Binding</span>
      </button>
      <button type="button" :class="{ active: mode === 'target' }" @click="mode = 'target'">
        <strong>替换人物 / 四视图</strong>
        <span>本土化人物设计、H3 四视图生成与采用</span>
      </button>
    </nav>

    <SourceCharacterAssetLibraryV1 v-if="mode === 'source'" :project-id="props.projectId" />
    <TargetCharacterAssetPanelV1 v-else :project-id="props.projectId" />
  </section>
</template>

<style scoped>
.character-asset-entry { min-height: 100%; padding: 14px 22px 24px; background: #f6f8fb; }
.character-asset-entry__intro {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) auto;
  gap: 20px;
  align-items: center;
  margin-bottom: 10px;
  padding: 16px 18px;
  border: 1px solid #dce4ef;
  border-radius: 14px;
  background: #fff;
}
.character-asset-entry__intro small { color: #6d7d94; font-size: 11px; font-weight: 800; letter-spacing: .05em; }
.character-asset-entry__intro h2 { margin: 4px 0 6px; color: #263a57; font-size: 18px; }
.character-asset-entry__intro p { max-width: 780px; margin: 0; color: #6e7d91; font-size: 12px; line-height: 1.7; }
.character-asset-entry__flow { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; justify-content: flex-end; }
.character-asset-entry__flow span { padding: 7px 9px; border: 1px solid #dbe4f2; border-radius: 8px; background: #f7faff; color: #42608a; font-size: 11px; font-weight: 750; white-space: nowrap; }
.character-asset-entry__flow b { color: #9ba8ba; font-size: 11px; }
.character-asset-tabs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
.character-asset-tabs button { display: grid; gap: 2px; min-height: 54px; padding: 8px 12px; border: 1px solid #dde3eb; border-radius: 10px; background: #fff; color: #536176; text-align: left; cursor: pointer; }
.character-asset-tabs button:hover { border-color: #bfcce0; background: #fafcff; }
.character-asset-tabs button.active { border-color: #8fa9df; background: #eef4ff; box-shadow: inset 3px 0 0 #5d82d6; }
.character-asset-tabs strong { color: #354965; font-size: 13px; }
.character-asset-tabs span { color: #8490a2; font-size: 10px; }
@media (max-width: 1000px) {
  .character-asset-entry__intro { grid-template-columns: 1fr; }
  .character-asset-entry__flow { justify-content: flex-start; }
  .character-asset-tabs { grid-template-columns: 1fr; }
}
</style>
