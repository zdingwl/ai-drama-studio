import { describe, expect, it } from 'vitest'
import { shotSpeakerCandidates } from './shotSpeakerCandidates'

const candidates = [
  { person_key: 'P1', character_id: 'xu', visible_in_shot: false },
  { person_key: 'P4', character_id: 'xu', visible_in_shot: true },
  { person_key: 'P5', character_id: 'xu', visible_in_shot: false },
  { person_key: 'P2', character_id: 'wang' },
  { person_key: 'P3', character_id: null },
]
describe('当前镜头说话人候选', () => {
  it('只显示绑定身份并去重，保留当前出镜的观察来源', () => {
    expect(shotSpeakerCandidates(candidates, ['xu']).map(p => p.person_key)).toEqual(['P4'])
  })
  it('空镜不自动展示整场人物', () => {
    expect(shotSpeakerCandidates(candidates, [])).toEqual([])
  })
  it('显式画外入口显示其他已确认身份，不含未绑定人物', () => {
    expect(shotSpeakerCandidates(candidates, ['xu'], true).map(p => p.character_id)).toEqual(['wang'])
  })
  it('无镜头绑定时画外入口仍按正式 ID 去重', () => {
    expect(shotSpeakerCandidates(candidates, [], true)).toHaveLength(2)
  })
})
