import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules() })

describe('拉片命令重放', () => {
  it('网络断开后沿用同一请求标识和输入，不重新启动一份任务', async () => {
    const context = {workflow_revision:'r1',input_fingerprint:'f1'}
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ok:true,json:async()=>context})
      .mockRejectedValueOnce(new TypeError('connection lost'))
      .mockResolvedValueOnce({ok:true,json:async()=>({id:'TASK_1'})})
    vi.stubGlobal('fetch', fetchMock)
    const {breakdownApi} = await import('./breakdown')
    await expect(breakdownApi.startShot('EPISODE', 3)).rejects.toThrow('connection lost')
    expect(await breakdownApi.startShot('EPISODE', 3)).toEqual({id:'TASK_1'})
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(fetchMock.mock.calls[2]?.[1])
    expect(fetchMock.mock.calls[0]?.[0]).toContain('shot_ordinal=3')
  })

  it('服务端拒绝旧版本后重新读取命令上下文', async () => {
    const fetchMock=vi.fn()
      .mockResolvedValueOnce({ok:true,json:async()=>({workflow_revision:'old',input_fingerprint:'old'})})
      .mockResolvedValueOnce({ok:false,status:409,json:async()=>({detail:'版本已变化'})})
      .mockResolvedValueOnce({ok:true,json:async()=>({workflow_revision:'new',input_fingerprint:'new'})})
      .mockResolvedValueOnce({ok:true,json:async()=>({id:'TASK_2'})})
    vi.stubGlobal('fetch',fetchMock)
    const {breakdownApi}=await import('./breakdown')
    await expect(breakdownApi.startEpisode('EPISODE')).rejects.toThrow('版本已变化')
    await breakdownApi.startEpisode('EPISODE')
    expect(JSON.parse(fetchMock.mock.calls[3]?.[1].body)).toEqual({workflow_revision:'new',input_fingerprint:'new'})
  })
})
