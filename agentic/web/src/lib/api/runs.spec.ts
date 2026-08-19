import { beforeEach, describe, expect, it, vi } from 'vitest'
import { get } from './fetch'
import { runsApi } from './runs'

vi.mock('./fetch', () => ({
  get: vi.fn(),
}))

describe('runsApi', () => {
  beforeEach(() => {
    vi.mocked(get).mockResolvedValue({})
  })

  it('requests incremental execution updates with explicit detail level', async () => {
    await runsApi.getExecution('run-1', { after: 7, limit: 25, detail: 'detail' })

    expect(get).toHaveBeenCalledWith('/runs/run-1/execution', {
      after: 7,
      limit: 25,
      detail: 'detail',
    })
  })

  it('forwards independent cursors for technical subresources', async () => {
    await runsApi.listEvents('run-1', { after: 8, limit: 10 })
    await runsApi.listToolCalls('run-1', { after: 'tool-1', limit: 11 })
    await runsApi.listModelCalls('run-1', { after: 'model-1', limit: 12 })

    expect(get).toHaveBeenNthCalledWith(1, '/runs/run-1/events', { after: 8, limit: 10 })
    expect(get).toHaveBeenNthCalledWith(2, '/runs/run-1/tool-calls', {
      after: 'tool-1',
      limit: 11,
    })
    expect(get).toHaveBeenNthCalledWith(3, '/runs/run-1/model-calls', {
      after: 'model-1',
      limit: 12,
    })
  })

  it('unwraps the run skills envelope', async () => {
    vi.mocked(get).mockResolvedValue({ skills: [{ id: 'skill-1' }] })

    await expect(runsApi.listSkills('run-1')).resolves.toEqual([{ id: 'skill-1' }])
    expect(get).toHaveBeenCalledWith('/runs/run-1/skills')
  })
})
