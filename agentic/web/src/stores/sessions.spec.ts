import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionApi } from '@/lib/api/session'
import type { Session } from '@/lib/api/types'
import { useSessionsStore } from './sessions'

function session(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 'session-1',
    title: 'Original',
    latest_message: 'latest',
    latest_message_at: '2026-07-24T10:00:00',
    status: 'completed',
    unread_message_count: 0,
    is_pinned: false,
    archived_at: null,
    has_next_message: false,
    ...overrides,
  }
}

describe('sessions store organization', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('updates active metadata and sorts pinned sessions first', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [
        session({ session_id: 'newer', latest_message_at: '2026-07-24T12:00:00' }),
        session({ session_id: 'older', latest_message_at: '2026-07-23T12:00:00' }),
      ],
    })
    const store = useSessionsStore()
    await store.refresh()
    vi.spyOn(sessionApi, 'updateOrganization').mockResolvedValue(
      session({
        session_id: 'older',
        title: 'Pinned',
        latest_message_at: '2026-07-23T12:00:00',
        is_pinned: true,
      }),
    )

    await store.updateOrganization('older', { pinned: true })

    expect(store.sessions.map((item) => item.session_id)).toEqual(['older', 'newer'])
    expect(store.sessions[0].title).toBe('Pinned')
  })

  it('preserves server order when business timestamps are tied', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [
        session({ session_id: 'server-first', latest_message_at: null }),
        session({ session_id: 'server-second', latest_message_at: null }),
      ],
    })
    const store = useSessionsStore()

    await store.refresh()

    expect(store.sessions.map((item) => item.session_id)).toEqual([
      'server-first',
      'server-second',
    ])
  })

  it('removes archived sessions and preserves state when the request fails', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [session()],
    })
    const store = useSessionsStore()
    await store.refresh()
    vi.spyOn(sessionApi, 'updateOrganization').mockResolvedValueOnce(
      session({ archived_at: '2026-07-24T13:00:00' }),
    )

    await store.updateOrganization('session-1', { archived: true })
    expect(store.sessions).toEqual([])
    expect(store.archivedSessions.map((item) => item.session_id)).toEqual([
      'session-1',
    ])

    await store.refresh()
    vi.mocked(sessionApi.updateOrganization).mockRejectedValueOnce(
      new Error('busy'),
    )
    await expect(
      store.updateOrganization('session-1', { archived: true }),
    ).rejects.toThrow('busy')
    expect(store.sessions).toHaveLength(1)
  })

  it('loads archived scope and moves a restored session back to active', async () => {
    vi.spyOn(sessionApi, 'getSessions').mockResolvedValue({
      sessions: [session({ archived_at: '2026-07-24T13:00:00' })],
    })
    const store = useSessionsStore()
    await store.loadArchivedSessions()
    expect(sessionApi.getSessions).toHaveBeenCalledWith('archived')
    expect(store.archivedSessions).toHaveLength(1)

    vi.spyOn(sessionApi, 'updateOrganization').mockResolvedValue(
      session({ archived_at: null }),
    )
    await store.updateOrganization('session-1', { archived: false })

    expect(store.archivedSessions).toEqual([])
    expect(store.sessions.map((item) => item.session_id)).toEqual(['session-1'])
  })
})
