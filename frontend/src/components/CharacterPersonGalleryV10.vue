<script setup lang="ts">
import CharacterAssetsWorkbenchV1 from './CharacterAssetsWorkbenchV1.vue'

const props = defineProps<{
  projectId: string
}>()
</script>

<template>
  <section class="character-asset-entry">
    <div class="character-asset-entry__intro">
      <div>
        <small>人物资产</small>
        <h2>原片人物归并与替换人物</h2>
        <p>
          分镜里识别到的人物只是证据。这里把同一个人的跨分镜观察归并成正式人物资产，
          并把人物资产绑定回所有出现的分镜；后续替换人物与四视图都从这里继续。
        </p>
      </div>
      <div class="character-asset-entry__flow" aria-label="人物资产流程">
        <span>分镜人物</span>
        <b>→</b>
        <span>人物归并</span>
        <b>→</b>
        <span>分镜绑定</span>
        <b>→</b>
        <span>替换人物</span>
        <b>→</b>
        <span>四视图</span>
      </div>
    </div>

    <CharacterAssetsWorkbenchV1 :project-id="props.projectId" />
  </section>
</template>

<style scoped>
.character-asset-entry {
  min-height: 100%;
  padding: 14px 22px 24px;
  background: #f6f8fb;
}

.character-asset-entry__intro {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) auto;
  gap: 20px;
  align-items: center;
  margin-bottom: 12px;
  padding: 16px 18px;
  border: 1px solid #dce4ef;
  border-radius: 14px;
  background: #fff;
}

.character-asset-entry__intro small {
  color: #6d7d94;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .05em;
}

.character-asset-entry__intro h2 {
  margin: 4px 0 6px;
  color: #263a57;
  font-size: 18px;
}

.character-asset-entry__intro p {
  max-width: 780px;
  margin: 0;
  color: #6e7d91;
  font-size: 12px;
  line-height: 1.7;
}

.character-asset-entry__flow {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: center;
  justify-content: flex-end;
}

.character-asset-entry__flow span {
  padding: 7px 9px;
  border: 1px solid #dbe4f2;
  border-radius: 8px;
  background: #f7faff;
  color: #42608a;
  font-size: 11px;
  font-weight: 750;
  white-space: nowrap;
}

.character-asset-entry__flow b {
  color: #9ba8ba;
  font-size: 11px;
}

@media (max-width: 1000px) {
  .character-asset-entry__intro { grid-template-columns: 1fr; }
  .character-asset-entry__flow { justify-content: flex-start; }
}
</style>
