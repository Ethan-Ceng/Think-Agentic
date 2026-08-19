import type {
  FailureInfo,
  RecoveryAction,
  ResumeMode,
} from '@/lib/api/types'
import type { SettingTab } from '@/lib/settings'

export type FailureRecoveryCommand =
  | { kind: 'resume'; mode: ResumeMode }
  | { kind: 'settings'; tab: SettingTab }

export type FailureRecoveryOption = {
  action: RecoveryAction
  label: string
  primary: boolean
  command: FailureRecoveryCommand
}

export function getFailureSettingsTab(failure: FailureInfo): SettingTab {
  if (failure.category === 'model' || failure.source.startsWith('llm')) return 'llm'
  if (failure.source.startsWith('mcp')) return 'mcp'
  if (failure.source.startsWith('a2a')) return 'a2a'
  if (failure.source.startsWith('api')) return 'tools'
  return 'common'
}

function optionForAction(
  action: RecoveryAction,
  failure: FailureInfo,
): Omit<FailureRecoveryOption, 'primary'> | null {
  switch (action) {
    case 'retry':
      return {
        action,
        label: '重试本次回复',
        command: { kind: 'resume', mode: 'continue' },
      }
    case 'continue':
      return {
        action,
        label: '从当前结果继续',
        command: { kind: 'resume', mode: 'continue' },
      }
    case 'start_new_run':
      return {
        action,
        label: '重新执行任务',
        command: { kind: 'resume', mode: 'restart' },
      }
    case 'check_config':
      return {
        action,
        label: '检查配置',
        command: { kind: 'settings', tab: getFailureSettingsTab(failure) },
      }
    case 'reauthorize':
      return {
        action,
        label: '重新配置连接',
        command: { kind: 'settings', tab: getFailureSettingsTab(failure) },
      }
    case 'choose_provider':
      return null
  }
}

function commandKey(command: FailureRecoveryCommand): string {
  return command.kind === 'resume'
    ? `resume:${command.mode}`
    : `settings:${command.tab}`
}

export function getFailureRecoveryOptions(
  failure?: FailureInfo | null,
): FailureRecoveryOption[] {
  if (!failure) {
    return [
      {
        action: 'retry',
        label: '重新生成回复',
        primary: true,
        command: { kind: 'resume', mode: 'continue' },
      },
      {
        action: 'start_new_run',
        label: '重新执行任务',
        primary: false,
        command: { kind: 'resume', mode: 'restart' },
      },
    ]
  }

  const seen = new Set<string>()
  const options: FailureRecoveryOption[] = []
  for (const action of failure.recovery_actions) {
    const option = optionForAction(action, failure)
    if (!option) continue
    const key = commandKey(option.command)
    if (seen.has(key)) continue
    seen.add(key)
    options.push({ ...option, primary: options.length === 0 })
  }
  return options
}
