import { describe, expect, it } from 'vitest'
import type { FailureInfo, RecoveryAction } from '@/lib/api/types'
import {
  getFailureRecoveryOptions,
  getFailureSettingsTab,
} from '@/lib/failure-recovery'

function failure(
  recoveryActions: RecoveryAction[],
  overrides: Partial<FailureInfo> = {},
): FailureInfo {
  return {
    code: 'PROVIDER_TIMEOUT',
    category: 'provider',
    scope: 'run',
    source: 'mcp',
    message: '外部工具服务响应超时。',
    retryable: true,
    recovery_actions: recoveryActions,
    debug_id: 'debug-1',
    ...overrides,
  }
}

describe('failure recovery registry', () => {
  it('keeps backend order while filtering actions without a real executor', () => {
    const options = getFailureRecoveryOptions(
      failure(['retry', 'choose_provider', 'check_config', 'start_new_run']),
    )

    expect(options.map((option) => option.action)).toEqual([
      'retry',
      'check_config',
      'start_new_run',
    ])
    expect(options[0]).toMatchObject({
      label: '重试本次回复',
      primary: true,
      command: { kind: 'resume', mode: 'continue' },
    })
    expect(options[1].command).toEqual({ kind: 'settings', tab: 'mcp' })
    expect(options[2].command).toEqual({ kind: 'resume', mode: 'restart' })
  })

  it('does not use retryable as a global action visibility switch', () => {
    const options = getFailureRecoveryOptions(
      failure(['check_config', 'start_new_run'], { retryable: false }),
    )

    expect(options.map((option) => option.action)).toEqual([
      'check_config',
      'start_new_run',
    ])
  })

  it('deduplicates actions that currently use the same executor', () => {
    const options = getFailureRecoveryOptions(
      failure(['retry', 'continue', 'check_config', 'reauthorize']),
    )

    expect(options.map((option) => option.action)).toEqual(['retry', 'check_config'])
  })

  it('preserves safe legacy recovery behavior without a FailureInfo', () => {
    const options = getFailureRecoveryOptions()

    expect(options.map((option) => option.label)).toEqual([
      '重新生成回复',
      '重新执行任务',
    ])
    expect(options.map((option) => option.command)).toEqual([
      { kind: 'resume', mode: 'continue' },
      { kind: 'resume', mode: 'restart' },
    ])
  })

  it('routes configuration repair to the matching settings panel', () => {
    expect(getFailureSettingsTab(failure([], { category: 'model', source: 'llm' }))).toBe('llm')
    expect(getFailureSettingsTab(failure([], { source: 'mcp' }))).toBe('mcp')
    expect(getFailureSettingsTab(failure([], { source: 'a2a' }))).toBe('a2a')
    expect(getFailureSettingsTab(failure([], { source: 'api' }))).toBe('tools')
    expect(getFailureSettingsTab(failure([], { source: 'runtime' }))).toBe('common')
  })
})
