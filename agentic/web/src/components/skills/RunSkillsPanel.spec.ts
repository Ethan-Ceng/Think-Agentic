import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { RunSkill } from '@/types/skill'
import type { TraceEventRecord } from '@/lib/api/types'
import RunSkillsPanel from './RunSkillsPanel.vue'

const skills: RunSkill[] = [
  {
    id: 'run-skill-1', run_id: 'run-1', skill_id: 'skill-1', skill_version_id: 'version-3',
    name: 'report-writer', source: 'personal', selection_mode: 'manual',
    content_sha256: 'a'.repeat(64), confidence: null, reason: 'Selected manually.',
    sandbox_path: '/home/ubuntu/.agentic/skills/run-1/report-writer', created_at: '2026-07-16T00:00:00Z',
  },
  {
    id: 'run-skill-2', run_id: 'run-1', skill_id: null, skill_version_id: null,
    name: 'pdf-reader', source: 'bundled', selection_mode: 'automatic',
    content_sha256: 'b'.repeat(64), confidence: 0.91, reason: 'Matched PDF attachment.',
    sandbox_path: '/home/ubuntu/.agentic/skills/run-1/pdf-reader', created_at: '2026-07-16T00:00:01Z',
  },
]

const event = (event_type: string, payload: Record<string, unknown>): TraceEventRecord => ({
  id: `${event_type}-1`, trace_id: 'trace-1', run_id: 'run-1', session_id: 'session-1',
  event_type, source: 'skill-runtime', payload, created_at: '2026-07-16T00:00:02Z',
})

describe('RunSkillsPanel', () => {
  it('shows manual and automatic decisions with immutable version evidence', () => {
    const wrapper = mount(RunSkillsPanel, { props: { skills, events: [] } })
    expect(wrapper.text()).toContain('手动选择')
    expect(wrapper.text()).toContain('自动识别')
    expect(wrapper.text()).toContain('version-3')
    expect(wrapper.text()).toContain('aaaaaaaaaaaa')
    expect(wrapper.text()).toContain('91%')
    expect(wrapper.text()).toContain('Matched PDF attachment.')
  })

  it('shows missing-tool skips and sanitized selection failures', () => {
    const wrapper = mount(RunSkillsPanel, {
      props: {
        skills: [],
        events: [
          event('skill.skipped', { name: 'shell-helper', code: 'missing_tools', reason: 'Required tools are unavailable: shell.' }),
          event('skill.selection.failed', { error_type: 'RuntimeError', message: 'Skill selection or materialization failed.' }),
        ],
      },
    })
    expect(wrapper.text()).toContain('shell-helper')
    expect(wrapper.text()).toContain('missing_tools')
    expect(wrapper.text()).toContain('Required tools are unavailable: shell.')
    expect(wrapper.text()).toContain('Skill selection or materialization failed.')
  })
})
