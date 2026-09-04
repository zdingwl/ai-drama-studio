import { describe, expect, it } from 'vitest'
import { groupPersonObservations, validPersonMark, type PersonObservation } from './personReviewGroups'
const row: PersonObservation = { key:'a', anchor:'v1', name:'人物', appearance:'女', episode_id:'e', episode_title:'EP01', character_id:null, suggested_character_id:'c', shots:[{id:'s',ordinal:1,thumbnail_url:'/frame'}] }
describe('person review groups', () => {
  it('keeps candidate suggestions separate from formal identities', () => {
    const result = groupPersonObservations([row,{...row,key:'b',character_id:'c'}],[{id:'c',name:'角色'}],{}, {})
    expect(result.map(g=>g.id)).toEqual(['candidate:c','formal:c'])
    expect(row.character_id).toBeNull()
  })
  it('moves the complete observation without dropping linked shots', () => {
    const input = {...row,shots:[...row.shots,{id:'s2',ordinal:2,thumbnail_url:'/other'}]}
    const result = groupPersonObservations([input],[],{a:'draft:1'}, {})
    expect(result[0]?.rows[0]?.shots).toHaveLength(2)
    expect(result[0]?.id).toBe('draft:1')
    expect(input.character_id).toBeNull()
  })
  it('never groups a mixed-person observation from an AI recommendation', () => {
    expect(groupPersonObservations([{...row,identity_issue:'多人'}],[],{}, {a:{character_id:'c'}})[0]?.id).toBe('unassigned')
  })
  it('accepts only finite current-frame normalized marks', () => {
    const mark = {shot_id:'s',image_url:'/frame',box:[.1,.1,.5,.5]}
    expect(validPersonMark(row,mark)).toBe(true)
    expect(validPersonMark(row,{...mark,image_url:'/old'})).toBe(false)
    expect(validPersonMark(row,{...mark,box:[0,0,2,1]})).toBe(false)
    expect(validPersonMark(row,{...mark,box:[0,0,NaN,1]})).toBe(false)
  })
})
