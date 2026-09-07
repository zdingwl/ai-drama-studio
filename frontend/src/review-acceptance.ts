import './styles.css'
import './studio-v3.css'
import './f05.css'
import './shot-manager.css'
import './shot-revision.css'
import './shot-workbench-v3.css'
import './shot-workbench-v3-overrides.css'
import './shot-workbench-v4.css'
import './asset-workbench-v3.css'
import './asset-review-matrix-v4.css'
import './asset-review-matrix-v4-overrides.css'
import './asset-image-lightbox.css'
import './task-progress.css'
import './breakdown-p3-acceptance.css'
import './breakdown-p3-v2-layout-fix.css'
import './breakdown-p3-v2-polish.css'
import './scene-timeline-g2-6-overrides.css'
import './product-readability.css'
import './source-video-page-fixes.css'
import './source-video-breakdown-navigation.css'
import './project-breakdown-shell-sync.css'
import './project-breakdown-shell-consistency.css'
import './workflow-stage-shell.css'
import './breakdown-manual-editor.css'
import './source-video-help-drawer.css'
import { createApp, h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import Overlay from './components/SourceConfirmOverlayV4.vue'
const ep = { id: 'acceptance-episode', title: '隔离验收（仅内存数据）', sort_order: 1 }
const base = '/api/shots/SHOT_7a64d6e46e0b467792a6bf5c779fc46b'
const shots = [1,2].map(n => ({ id: 'shot'+n, ordinal: n, start_us: (n-1)*1000000, end_us:n*1000000, thumbnail_url:base+'/thumbnail',reference_url:base+'/reference' }))
let observations = ['甲','乙'].map((name,i) => ({ key:'person'+i,name:'验收观察'+name,appearance:'当前原图中的人物，仅用于隔离界面验收',episode_id:ep.id, character_id:null,shots:[shots[i]] }))
const characters = [{id:'character',name:'验收正式人物',cover_url:base+'/thumbnail',shot_ids:['shot1','shot2']}]
let evidence = [1,2].map(n=>({id:'evidence'+n,status:'OPEN',revision:'r',start_us:n*100000,end_us:n*100000+300000,asr_text:'语音示例'+n,subtitle_text:'字幕示例'+n,utterance_id:'utterance'+n}))
let issues = [1,2].map(n=>({id:'issue'+n,issue_type:'SPEAKER',shot_id:'shot1',episode_id:ep.id,ai_suggestion:{dialogue_key:'d'+n,source_text:'说话人示例'+n,dialogue_start_us:n*100000,candidate_people:[{person_key:'person0',character_id:'character',character_name:'验收正式人物',cover_url:base+'/thumbnail',visible_in_shot:true}]}}))
window.fetch = async (input, init) => {
 const path = String(input); const data = init?.body ? JSON.parse(String(init.body)) : {}
 let result: unknown = null
 if(path.endsWith('/character-assets/assign')) { observations = observations.map(o=>data.keys.includes(o.key)?{...o,character_id:'character'}:o) as typeof observations; result={revision:'r',observations,characters} }
 else if(path.endsWith('/character-assets')) result={revision:'r',observations,characters}
 else if(path.endsWith('/assets/workspace')) result={bindings_by_shot:Object.fromEntries(shots.map(s=>[s.id,{character_ids:['character'],scene_id:null,prop_ids:[]}])),evidence_by_shot:{},characters,scenes:[],props:[]}
 else if(path.endsWith('/shots')) result=shots
 else if(path.includes('/dialogue-evidence/') && path.endsWith('/decide')) {evidence=evidence.filter(e=>!path.includes('/'+e.id+'/'));result={ok:true}}
 else if(path.endsWith('/dialogue-evidence')) result=evidence
 else if(path.endsWith('/speaker')) {issues=issues.filter(i=>!path.includes('/'+i.id+'/'));result={ok:true}}
 else if(path.includes('/review-issues') || path.endsWith('/speaker-reviews/prepare')) result=issues
 else if(path.includes('flow-state')) result={schema_version:'project-flow-state-v1',project_id:'acceptance',episodes:[],revision:'r',stages:[],next_action:{reason:'隔离验收，不能进入重拍'}}
 else if(path.endsWith('/projects/acceptance')) result={id:'acceptance',episodes:[ep]}
 else throw new Error('隔离验收禁止未声明的请求：'+path)
 return new Response(JSON.stringify(result),{headers:{'Content-Type':'application/json'}})
}
const router=createRouter({history:createWebHistory(),routes:[{path:'/:pathMatch(.*)*',name:'breakdown',component:{render:()=>null}}]})
createApp({render:()=>h(Overlay,{projectId:'acceptance'})}).use(router).mount('#app')
