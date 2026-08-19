<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Archive, ArrowDown } from 'lucide-vue-next'
import { ElMessageBox } from 'element-plus'
import ArchivedSessionsDialog from '@/components/ArchivedSessionsDialog.vue'
import BranchVersionNavigator from '@/components/chat/BranchVersionNavigator.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import PlanPanel from '@/components/chat/PlanPanel.vue'
import ThinkingIndicator from '@/components/chat/ThinkingIndicator.vue'
import SessionHeader from '@/components/SessionHeader.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiState from '@/components/ui/UiState.vue'
import { useSessionDetail } from '@/composables/useSessionDetail'
import { useSettingsModal } from '@/composables/useSettingsModal'
import { useToast } from '@/composables/useToast'
import { sessionApi } from '@/lib/api/session'
import { ApiError } from '@/lib/api/fetch'
import type {
  BranchFamilyResponse,
  BranchOperation,
  ResolveInteractionParams,
  ResumeMode,
  ToolEvent,
} from '@/lib/api/types'
import type { InlineChatArtifact } from '@/lib/chat-artifacts'
import {
  canAutoFollowTool,
  type ChatPreviewSelection,
} from '@/lib/chat-preview'
import type { ComposerAttachmentMetadata } from '@/lib/composer-attachments'
import type { AttachmentFile, TimelineItem, UserMessageStatus } from '@/lib/session-events'
import type { SendMessageInput, SkillRef } from '@/types/skill'
import { eventsToTimeline, formatMessageTimeLabel, getLatestPlanFromEvents } from '@/lib/session-events'
import { getToolKind } from '@/lib/tool-utils'
import { createQueuedRunIntent } from '@/lib/session-init'
import type { FailureRecoveryCommand } from '@/lib/failure-recovery'

const props = withDefaults(defineProps<{
  sessionId: string
  initialMessage?: string
  initialAttachments?: string[]
  initialSkills?: SkillRef[]
  hasInitialMessage?: boolean
  runQueued?: boolean
}>(), {
  initialMessage: undefined,
  initialAttachments: () => [],
  initialSkills: () => [],
  hasInitialMessage: false,
  runQueued: false,
})

type PendingUserMessage = {
  id: string
  message: string
  attachmentIds: string[]
  skills: SkillRef[]
  files: AttachmentFile[]
  createdAt: number
  status: Exclude<UserMessageStatus, 'sent'>
  errorText?: string
}

const router = useRouter()
const route = useRoute()
const toast = useToast()
const settingsModal = useSettingsModal()
const FilePreviewPanel = defineAsyncComponent(() => import('@/components/FilePreviewPanel.vue'))
const ChatArtifactPreviewPanel = defineAsyncComponent(
  () => import('@/components/chat/ChatArtifactPreviewPanel.vue'),
)
const TracePanel = defineAsyncComponent(() => import('@/components/TracePanel.vue'))
const ToolPreviewPanel = defineAsyncComponent(() => import('@/components/chat/ToolPreviewPanel.vue'))
const VNCOverlay = defineAsyncComponent(() => import('@/components/VNCOverlay.vue'))
const fileListOpen = ref(false)
const previewSelection = ref<ChatPreviewSelection | null>(null)
const previewFile = computed(() =>
  previewSelection.value?.kind === 'file' ? previewSelection.value.file : null,
)
const previewTool = computed(() =>
  previewSelection.value?.kind === 'tool' ? previewSelection.value.tool : null,
)
const previewArtifact = computed(() =>
  previewSelection.value?.kind === 'artifact' ? previewSelection.value.artifact : null,
)
const traceOpen = computed(() => previewSelection.value?.kind === 'trace')
const vncOpen = ref(false)
const archivedDialogOpen = ref(false)
const initialMessageSent = ref(false)
const scrollContainerRef = ref<HTMLDivElement | null>(null)
const prevToolCount = ref(0)
const isNearBottom = ref(true)
const pendingUserMessage = ref<PendingUserMessage | null>(null)
const resolvingActionId = ref<string | null>(null)
const interactionErrors = ref<Record<string, string>>({})
const stoppedAt = ref<number | null>(null)
const queuedRunBusy = ref(false)
const queuedRunIntentHandled = ref(false)
const branchBusyEventId = ref<string | null>(null)
const editBranchItem = ref<Extract<TimelineItem, { kind: 'user' }> | null>(null)
const pendingBranchRequest = ref<{ signature: string; requestId: string } | null>(null)
const branchFamily = ref<BranchFamilyResponse | null>(null)
const branchFamilyLoading = ref(false)
const branchFamilyError = ref('')
const lastFocusedEvent = ref('')
let focusTimer = 0
let branchFamilyRequestVersion = 0

const detail = useSessionDetail(
  computed(() => props.sessionId),
  computed(() => props.hasInitialMessage || props.runQueued),
)

const baseTimeline = computed(() => eventsToTimeline(detail.events.value))
const isArchived = computed(() => Boolean(detail.session.value?.archived_at))
const branchEventQuery = computed(() => {
  const value = route.query.branchEvent
  return typeof value === 'string' ? value.trim() : ''
})
const showBranchVersionNavigator = computed(
  () =>
    Boolean(branchEventQuery.value) ||
    Boolean(detail.session.value?.branch_operation),
)
const timeline = computed<TimelineItem[]>(() => {
  const items = [...baseTimeline.value]
  const pending = pendingUserMessage.value

  if (pending && !hasMatchingUserMessage(items, pending)) {
    items.push({
      kind: 'user',
      id: pending.id,
      data: {
        role: 'user',
        message: pending.message,
        skills: pending.skills,
      },
      status: pending.status,
      statusText: getPendingStatusText(pending.status),
      errorText: pending.errorText,
      canRetry: pending.status === 'failed',
      timeLabel: formatMessageTimeLabel(pending.createdAt),
      createdAt: pending.createdAt,
    })

    if (pending.files.length > 0) {
      items.push({
        kind: 'attachments',
        id: `${pending.id}-attachments`,
        role: 'user',
        files: pending.files,
      })
    }
  }

  return items
})
const planSteps = computed(() => getLatestPlanFromEvents(detail.events.value))
const hasStreamingAssistantDraft = computed(() =>
  timeline.value.some((item) => item.kind === 'assistant' && item.streaming),
)
const pendingInteraction = computed(() => {
  for (let i = timeline.value.length - 1; i >= 0; i--) {
    const item = timeline.value[i]
    if (
      item.kind === 'interaction' &&
      item.data.interaction_type === 'ask_user' &&
      item.data.status === 'pending'
    ) return item.data
  }
  return null
})
const pendingInteractionBlocksComposer = computed(
  () => Boolean(pendingInteraction.value && !pendingInteraction.value.allow_text),
)
const latestRecoverableErrorId = computed(() => {
  if (detail.session.value?.status !== 'completed') return null
  for (let i = timeline.value.length - 1; i >= 0; i--) {
    if (timeline.value[i].kind === 'error') return timeline.value[i].id
  }
  return null
})
const hasPreview = computed(() => previewSelection.value !== null)
const showJumpToBottom = computed(
  () =>
    !isNearBottom.value &&
    (timeline.value.length > 0 || detail.streaming.value || detail.session.value?.status === 'running'),
)
const runningStateLabel = computed(() => {
  if (stoppedAt.value) {
    return `任务已停止 · ${formatMessageTimeLabel(stoppedAt.value) || '刚刚'}`
  }
  if (detail.error.value && detail.session.value) {
    return `响应中断：${detail.error.value.message}`
  }
  if (detail.session.value?.status === 'waiting') {
    if (!pendingInteraction.value) return '旧审批已停用，可继续输入'
    return pendingInteraction.value.allow_text
      ? '等待你的回复 · 可直接在输入框回复或使用问题卡'
      : '等待你在问题卡中选择'
  }
  if (detail.session.value?.status === 'running') {
    return '正在生成回复'
  }
  return ''
})
const branchDisabledReason = computed(() => {
  if (isArchived.value) {
    return '任务已归档，恢复后才能创建分支'
  }
  if (detail.streaming.value || detail.session.value?.status === 'running') {
    return '任务执行中，完成后才能从历史消息创建分支'
  }
  if (detail.session.value?.status === 'waiting') {
    return pendingInteraction.value
      ? '请先回答当前问题'
      : '请先发送一条新消息，使旧审批安全结束'
  }
  if (detail.session.value?.next_message) {
    return '请先发送或取消已排队的下一条消息'
  }
  return ''
})
const branchDisabled = computed(
  () =>
    Boolean(branchDisabledReason.value) ||
    detail.session.value?.status !== 'completed',
)
const branchOperationLabel = computed(() => {
  switch (detail.session.value?.branch_operation) {
    case 'edit':
      return '编辑后创建的分支'
    case 'regenerate':
      return '重新生成回复的分支'
    default:
      return '从历史消息创建的分支'
  }
})

const SCROLL_BOTTOM_THRESHOLD = 96

function getPendingStatusText(status: PendingUserMessage['status']): string {
  switch (status) {
    case 'sending':
      return '发送中'
    case 'failed':
      return '发送失败'
    case 'stopped':
      return '已停止'
    default:
      return '已发送'
  }
}

function fileInfoToAttachment(file: ComposerAttachmentMetadata): AttachmentFile {
  return {
    id: file.id,
    filename: file.filename,
    extension: file.extension || file.filename.split('.').pop() || '',
    size: file.size,
  }
}

function createPendingMessage(
  message: string,
  attachmentIds: string[],
  files: AttachmentFile[] = [],
  skills: SkillRef[] = [],
): PendingUserMessage {
  return {
    id: `pending-${Date.now()}`,
    message,
    attachmentIds,
    skills,
    files,
    createdAt: Date.now(),
    status: 'sending',
  }
}

function hasMatchingUserMessage(items: TimelineItem[], pending: PendingUserMessage): boolean {
  return items.some((item) => {
    if (item.kind !== 'user') return false
    if ((item.data.message ?? '') !== pending.message) return false
    if (!item.createdAt) return false
    return item.createdAt >= pending.createdAt - 2 * 60 * 1000
  })
}

function markPendingFailed(itemId: string, error: unknown) {
  const pending = pendingUserMessage.value
  if (!pending || pending.id !== itemId) return

  pendingUserMessage.value = {
    ...pending,
    status: 'failed',
    errorText: error instanceof Error ? error.message : '发送失败，请检查连接后重试',
  }
}

async function sendPendingMessage(pending: PendingUserMessage) {
  if (isArchived.value) {
    throw new Error('任务已归档，请先恢复后再继续执行')
  }
  pendingUserMessage.value = {
    ...pending,
    status: 'sending',
    errorText: undefined,
  }

  try {
    await detail.sendMessage({
      message: pending.message,
      attachmentIds: pending.attachmentIds,
      skills: pending.skills,
    })
    isNearBottom.value = true
    scrollToConversationBottom('smooth')
  } catch (error) {
    markPendingFailed(pending.id, error)
    throw error
  }
}

function updateScrollState() {
  const el = scrollContainerRef.value
  if (!el) {
    isNearBottom.value = true
    return
  }
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  isNearBottom.value = distance <= SCROLL_BOTTOM_THRESHOLD
}

function scrollToConversationBottom(behavior: ScrollBehavior = 'smooth') {
  void nextTick(() => {
    const el = scrollContainerRef.value
    if (!el) return
    el.scrollTo({
      top: el.scrollHeight,
      behavior,
    })
    isNearBottom.value = true
  })
}

function followConversationBottom(behavior: ScrollBehavior = 'smooth') {
  if (isNearBottom.value) {
    scrollToConversationBottom(behavior)
  }
}

function handleConversationScroll() {
  updateScrollState()
}

function findLatestTool(items: TimelineItem[]): ToolEvent | null {
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i]
    if (item.kind === 'tool' && getToolKind(item.data) !== 'message') {
      return item.data
    }
    if (item.kind === 'step') {
      for (let j = item.tools.length - 1; j >= 0; j--) {
        if (getToolKind(item.tools[j]) !== 'message') {
          return item.tools[j]
        }
      }
    }
  }
  return null
}

const resolvedPreviewTool = computed(() => {
  if (!previewTool.value) return null
  const id = (previewTool.value as { tool_call_id?: string }).tool_call_id
  if (!id) return previewTool.value

  for (let i = timeline.value.length - 1; i >= 0; i--) {
    const item = timeline.value[i]
    if (item.kind === 'tool' && (item.data as { tool_call_id?: string }).tool_call_id === id) {
      return item.data
    }
    if (item.kind === 'step') {
      const found = item.tools.find((tool) => (tool as { tool_call_id?: string }).tool_call_id === id)
      if (found) return found
    }
  }
  return previewTool.value
})

watch(
  () => [timeline.value, detail.session.value?.status, vncOpen.value] as const,
  () => {
    if (detail.session.value?.status !== 'running' || vncOpen.value) return

    const latestTool = findLatestTool(timeline.value)
    const toolCount = timeline.value.reduce((count, item) => {
      if (item.kind === 'tool') return count + 1
      if (item.kind === 'step') return count + item.tools.length
      return count
    }, 0)

    if (
      toolCount > prevToolCount.value &&
      latestTool &&
      canAutoFollowTool(previewSelection.value)
    ) {
      const shouldFollow = isNearBottom.value
      previewSelection.value = {
        kind: 'tool',
        source: 'auto',
        tool: latestTool,
      }
      if (shouldFollow) scrollToConversationBottom('smooth')
    }
    prevToolCount.value = toolCount
  },
)

watch(
  () => [props.initialMessage, detail.session.value, detail.loading.value, detail.streaming.value] as const,
  () => {
    if (
      props.initialMessage &&
      !initialMessageSent.value &&
      detail.session.value &&
      !isArchived.value &&
      !detail.loading.value &&
      !detail.streaming.value
    ) {
      initialMessageSent.value = true
      const pending = createPendingMessage(
        props.initialMessage,
        props.initialAttachments || [],
        [],
        props.initialSkills || [],
      )
      pendingUserMessage.value = pending
      stoppedAt.value = null
      isNearBottom.value = true
      scrollToConversationBottom('auto')

      detail
        .sendMessage({
          message: pending.message,
          attachmentIds: pending.attachmentIds,
          skills: pending.skills,
        })
        .then(() => {
          window.setTimeout(() => {
            void router.replace(`/sessions/${props.sessionId}`)
          }, 100)
        })
        .catch((error) => {
          markPendingFailed(pending.id, error)
          toast.error(error instanceof Error ? error.message : '发送消息失败')
        })
    }
  },
  { immediate: true },
)

watch(
  baseTimeline,
  (items) => {
    const editing = editBranchItem.value
    if (
      editing?.sourceEventId &&
      !items.some((item) => item.sourceEventId === editing.sourceEventId)
    ) {
      editBranchItem.value = null
    }

    const pending = pendingUserMessage.value
    if (!pending) return
    if (hasMatchingUserMessage(items, pending)) {
      pendingUserMessage.value = null
    }
  },
)

watch(branchDisabled, (disabled) => {
  if (disabled && !branchBusyEventId.value) {
    editBranchItem.value = null
  }
})

watch(
  () => detail.error.value,
  (error) => {
    const pending = pendingUserMessage.value
    if (error && pending?.status === 'sending') {
      markPendingFailed(pending.id, error)
    }
  },
)

watch(
  () => [detail.events.value.length, detail.streaming.value, detail.session.value?.status] as const,
  () => {
    followConversationBottom('smooth')
  },
)

watch(
  () => props.sessionId,
  () => {
    branchFamilyRequestVersion += 1
    branchFamily.value = null
    branchFamilyLoading.value = false
    branchFamilyError.value = ''
    pendingUserMessage.value = null
    resolvingActionId.value = null
    interactionErrors.value = {}
    stoppedAt.value = null
    isNearBottom.value = true
    lastFocusedEvent.value = ''
    queuedRunIntentHandled.value = false
    editBranchItem.value = null
    branchBusyEventId.value = null
    pendingBranchRequest.value = null
    scrollToConversationBottom('auto')
  },
)

async function loadBranchFamily(targetEventId?: string) {
  const requestVersion = ++branchFamilyRequestVersion
  branchFamilyLoading.value = true
  branchFamilyError.value = ''
  try {
    const family = await sessionApi.getBranchFamily(
      props.sessionId,
      targetEventId,
    )
    if (requestVersion !== branchFamilyRequestVersion) return
    branchFamily.value = family
  } catch (error) {
    if (requestVersion !== branchFamilyRequestVersion) return
    branchFamily.value = null
    branchFamilyError.value =
      error instanceof Error ? error.message : '暂时无法加载对话版本'
  } finally {
    if (requestVersion === branchFamilyRequestVersion) {
      branchFamilyLoading.value = false
    }
  }
}

function retryBranchFamily() {
  void loadBranchFamily(branchEventQuery.value || undefined)
}

watch(
  () => [
    props.sessionId,
    branchEventQuery.value,
    detail.session.value?.branch_operation,
    detail.loading.value,
  ] as const,
  ([, targetEventId, operation, loading]) => {
    if (loading || !detail.session.value) return
    if (!targetEventId && !operation) {
      branchFamilyRequestVersion += 1
      branchFamily.value = null
      branchFamilyLoading.value = false
      branchFamilyError.value = ''
      return
    }
    void loadBranchFamily(targetEventId || undefined)
  },
  { immediate: true },
)

watch(
  () => [route.query.focus, timeline.value.length, detail.loading.value] as const,
  ([focus, , loading]) => {
    if (typeof focus !== 'string' || !focus || loading) return
    const focusKey = `${props.sessionId}:${focus}`
    if (lastFocusedEvent.value === focusKey) return
    void nextTick(() => {
      const target = document.getElementById(`event-${focus}`)
      if (!target) return
      lastFocusedEvent.value = focusKey
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.classList.add('search-target-flash')
      window.clearTimeout(focusTimer)
      focusTimer = window.setTimeout(() => target.classList.remove('search-target-flash'), 1800)
    })
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  branchFamilyRequestVersion += 1
  window.clearTimeout(focusTimer)
})

async function handleSend(input: SendMessageInput, uploadedFiles: ComposerAttachmentMetadata[]) {
  if (isArchived.value) {
    toast.info('任务已归档，请先从归档管理中恢复')
    throw new Error('任务已归档，请先恢复后再继续执行')
  }
  if (detail.session.value?.status === 'running') {
    const replacingQueuedMessage = Boolean(detail.session.value.next_message)
    try {
      await detail.queueNextMessage(input)
      stoppedAt.value = null
      toast.success(replacingQueuedMessage ? '下一条消息已更新' : '已加入下一条消息')
      return
    } catch (error) {
      if (error instanceof ApiError && error.code === 409) {
        await detail.refresh()
        if (
          detail.session.value?.status !== 'running' &&
          !detail.session.value?.next_message
        ) {
          // The active run won the row-lock race. Fall through to a normal send.
        } else {
          toast.error(error.message)
          throw error
        }
      } else {
        toast.error(error instanceof Error ? error.message : '保存下一条消息失败')
        throw error
      }
    }
  }

  const pending = createPendingMessage(
    input.message,
    input.attachmentIds,
    uploadedFiles.map(fileInfoToAttachment),
    input.skills,
  )
  pendingUserMessage.value = pending
  stoppedAt.value = null

  try {
    await sendPendingMessage(pending)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '发送失败，请重试')
    throw error
  }
}

async function handleRetryMessage(itemId: string) {
  const pending = pendingUserMessage.value
  if (!pending || pending.id !== itemId || pending.status !== 'failed') return

  try {
    await sendPendingMessage(pending)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '重试失败，请稍后再试')
  }
}

function handleViewAllFiles() {
  void detail.refreshFiles()
  fileListOpen.value = true
}

function handleFileClick(file: AttachmentFile) {
  previewSelection.value = {
    kind: 'file',
    source: 'user',
    file,
  }
}

async function handleRecoverTask(mode: ResumeMode) {
  if (isArchived.value) {
    toast.info('任务已归档，请先从归档管理中恢复')
    return
  }
  if (detail.streaming.value || detail.session.value?.status === 'running') return

  if (mode === 'restart') {
    try {
      await ElMessageBox.confirm(
        '将基于当前对话的原始需求从头执行，并创建一个新的运行记录。已产生的文件不会自动删除。',
        '从头重新执行任务？',
        {
          confirmButtonText: '重新执行',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch {
      return
    }
  }

  stoppedAt.value = null
  try {
    await detail.resumeTask(mode)
    isNearBottom.value = true
    scrollToConversationBottom('smooth')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '恢复任务失败，请稍后再试')
  }
}

async function handleFailureRecovery(command: FailureRecoveryCommand) {
  if (command.kind === 'settings') {
    settingsModal.openSettings(command.tab, command.failure)
    return
  }
  await handleRecoverTask(command.mode)
}

async function handleCancelNextMessage() {
  if (detail.session.value?.next_message?.state === 'processing') return
  try {
    await detail.cancelNextMessage()
    toast.success('下一条消息已取消')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '取消下一条消息失败')
  }
}

async function handleRunNextMessage() {
  if (isArchived.value) {
    toast.info('任务已归档，请先从归档管理中恢复')
    return
  }
  if (queuedRunBusy.value) return
  queuedRunBusy.value = true
  stoppedAt.value = null
  try {
    await detail.runNextMessage()
  } catch (error) {
    if (error instanceof ApiError && error.code === 409) {
      await detail.refresh()
    } else {
      toast.error(error instanceof Error ? error.message : '恢复下一条消息失败')
    }
  } finally {
    queuedRunBusy.value = false
  }
}

async function createBranch(
  operation: BranchOperation,
  item: TimelineItem,
  message?: string,
) {
  if (
    branchBusyEventId.value ||
    (item.kind !== 'user' && item.kind !== 'assistant') ||
    !item.sourceEventId ||
    branchDisabled.value
  ) return

  branchBusyEventId.value = item.sourceEventId
  try {
    const requestSignature = JSON.stringify({
      sessionId: props.sessionId,
      operation,
      targetEventId: item.sourceEventId,
      message: operation === 'edit' ? message : undefined,
    })
    if (pendingBranchRequest.value?.signature !== requestSignature) {
      pendingBranchRequest.value = {
        signature: requestSignature,
        requestId: crypto.randomUUID(),
      }
    }
    const result = await sessionApi.createBranch(props.sessionId, {
      operation,
      target_event_id: item.sourceEventId,
      request_id: pendingBranchRequest.value.requestId,
      ...(operation === 'edit' ? { message } : {}),
    })
    editBranchItem.value = null
    const queuedIntent = result.queued
      ? createQueuedRunIntent(result.session_id)
      : ''
    const query: Record<string, string> = {
      branchEvent: result.forked_from_event_id,
    }
    if (queuedIntent) query.runQueued = queuedIntent
    await router.push({
      path: `/sessions/${result.session_id}`,
      query,
    })
    pendingBranchRequest.value = null
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '创建会话分支失败')
  } finally {
    branchBusyEventId.value = null
  }
}

function handleBranchAction(operation: BranchOperation, item: TimelineItem) {
  if (item.kind !== 'user' && item.kind !== 'assistant') return
  if (operation === 'edit' && item.kind === 'user') {
    if (!item.sourceEventId || branchDisabled.value || branchBusyEventId.value) return
    editBranchItem.value = item
    return
  }
  void createBranch(operation, item)
}

function handleEditBranchSubmit(message: string) {
  const item = editBranchItem.value
  if (!item) return
  void createBranch('edit', item, message)
}

function cancelEditBranch() {
  if (!branchBusyEventId.value) editBranchItem.value = null
}

function clearRunQueuedQuery() {
  const { runQueued: _runQueued, ...query } = route.query
  void router.replace({ path: route.path, query })
}

function navigateToBranchVersion(sessionId: string) {
  const family = branchFamily.value
  if (!family || sessionId === props.sessionId) return
  const query =
    sessionId === family.source_session_id
      ? { branchEvent: family.target_event_id }
      : undefined
  void router.push({
    path: `/sessions/${sessionId}`,
    query,
  })
}

function navigateToBranchSource() {
  const sourceSessionId = detail.session.value?.source_session_id
  if (!sourceSessionId) return
  const targetEventId = detail.session.value?.forked_from_event_id
  void router.push({
    path: `/sessions/${sourceSessionId}`,
    query: targetEventId ? { branchEvent: targetEventId } : undefined,
  })
}

function closeBranchVersionContext() {
  const { branchEvent: _branchEvent, ...query } = route.query
  void router.replace({
    path: route.path,
    query,
  })
}

watch(
  () => [
    props.runQueued,
    detail.loading.value,
    detail.session.value?.status,
    detail.session.value?.next_message?.state,
  ] as const,
  ([runQueued, loading, status, nextMessageState]) => {
    if (!runQueued || loading || !detail.session.value || queuedRunIntentHandled.value) return
    queuedRunIntentHandled.value = true
    clearRunQueuedQuery()
    if (status === 'completed' && nextMessageState === 'queued') {
      void handleRunNextMessage()
    }
  },
  { immediate: true },
)

async function handleResolveInteraction(actionId: string, params: ResolveInteractionParams) {
  if (resolvingActionId.value) return
  resolvingActionId.value = actionId
  interactionErrors.value = { ...interactionErrors.value, [actionId]: '' }
  try {
    await detail.resolveInteraction(actionId, params)
    isNearBottom.value = true
    scrollToConversationBottom('smooth')
  } catch (resolveError) {
    interactionErrors.value = {
      ...interactionErrors.value,
      [actionId]: resolveError instanceof Error ? resolveError.message : '处理失败，请重试',
    }
  } finally {
    resolvingActionId.value = null
  }
}

function handleToolClick(tool: ToolEvent) {
  if (getToolKind(tool) === 'message') return
  previewSelection.value = {
    kind: 'tool',
    source: 'user',
    tool,
  }
}

function handleArtifactOpen(artifact: InlineChatArtifact) {
  previewSelection.value = {
    kind: 'artifact',
    source: 'user',
    artifact,
  }
}

function closePreview() {
  previewSelection.value = null
}

function openTracePanel() {
  previewSelection.value = {
    kind: 'trace',
    source: 'user',
  }
}

function jumpToLatest() {
  const latest = findLatestTool(timeline.value)
  if (latest) {
    previewSelection.value = {
      kind: 'tool',
      source: 'auto',
      tool: latest,
    }
  }
  scrollContainerRef.value?.scrollTo({
    top: scrollContainerRef.value.scrollHeight,
    behavior: 'smooth',
  })
  isNearBottom.value = true
}

function closeVNC() {
  vncOpen.value = false
  const latest = findLatestTool(timeline.value)
  if (
    latest &&
    detail.session.value?.status === 'running' &&
    canAutoFollowTool(previewSelection.value)
  ) {
    previewSelection.value = {
      kind: 'tool',
      source: 'auto',
      tool: latest,
    }
    window.setTimeout(() => {
      scrollContainerRef.value?.scrollTo({
        top: scrollContainerRef.value.scrollHeight,
        behavior: 'smooth',
      })
    }, 100)
  }
}

watch(
  () => props.sessionId,
  (sessionId, previousSessionId) => {
    if (!previousSessionId || sessionId === previousSessionId) return
    previewSelection.value = null
    vncOpen.value = false
    prevToolCount.value = 0
  },
)

async function handleStop() {
  if (!detail.session.value) return
  try {
    await sessionApi.stopSession(props.sessionId)
    stoppedAt.value = Date.now()
    if (pendingUserMessage.value?.status === 'sending') {
      pendingUserMessage.value = {
        ...pendingUserMessage.value,
        status: 'stopped',
        errorText: undefined,
      }
    }
    toast.success('任务已停止')
    await detail.refresh()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '停止任务失败')
  }
}
</script>

<template>
  <div v-if="detail.loading.value && !detail.session.value" class="page-state">
    <ThinkingIndicator
      v-if="hasInitialMessage"
      title="正在创建任务"
      description="MoocManus 正在读取你的初始问题"
    />
    <UiState v-else kind="loading" title="正在加载任务" description="正在读取会话和执行记录。" />
  </div>

  <UiState v-else-if="detail.error.value && !detail.session.value" class="page-state" kind="error" title="任务加载失败" :description="detail.error.value.message">
    <template #actions><UiButton @click="detail.refresh">重试</UiButton></template>
  </UiState>

  <UiState v-else-if="!detail.session.value" class="page-state" title="未找到该任务" description="任务可能已被删除，或当前账号没有访问权限。" />

  <template v-else>
    <div class="session-workspace">
      <section class="conversation-pane">
        <div class="conversation-inner" :class="{ compact: hasPreview }">
          <SessionHeader
            v-model:file-list-open="fileListOpen"
            :title="detail.session.value.title"
            :files="detail.files.value"
            :status="detail.session.value.status"
            :on-fetch-files="detail.refreshFiles"
            @file-click="handleFileClick"
            @open-trace="openTracePanel"
          />
          <div
            v-if="isArchived"
            class="archived-session-banner"
            role="status"
          >
            <Archive :size="16" aria-hidden="true" />
            <span>此任务已归档。恢复后才能继续发送消息或重新执行。</span>
            <button type="button" @click="archivedDialogOpen = true">
              管理已归档任务
            </button>
          </div>
          <BranchVersionNavigator
            v-if="showBranchVersionNavigator"
            :family="branchFamily"
            :loading="branchFamilyLoading"
            :error="branchFamilyError"
            :lineage-label="branchOperationLabel"
            :source-session-id="detail.session.value.source_session_id"
            :source-session-title="detail.session.value.source_session_title"
            :closable="Boolean(branchEventQuery)"
            @navigate="navigateToBranchVersion"
            @navigate-source="navigateToBranchSource"
            @retry="retryBranchFamily"
            @close="closeBranchVersionContext"
          />

          <div
            ref="scrollContainerRef"
            class="conversation-scroll"
            :aria-busy="detail.streaming.value || detail.session.value.status === 'running'"
            @scroll.passive="handleConversationScroll"
          >
            <div class="timeline">
              <UiState
                v-if="timeline.length === 0 && !detail.streaming.value && !hasInitialMessage"
                class="timeline-empty"
                compact
                title="暂无对话记录"
                description="在下方输入任务或提问。"
              />

              <ChatMessage
                v-for="item in timeline"
                :key="item.id"
                :item="item"
                :dom-id="item.sourceEventId ? `event-${item.sourceEventId}` : undefined"
                :show-recovery-actions="
                  !isArchived &&
                  item.kind === 'error' &&
                  item.id === latestRecoverableErrorId
                "
                :recovery-busy="detail.streaming.value"
                :interaction-busy="item.kind === 'interaction' && resolvingActionId === item.data.action_id"
                :interaction-error="item.kind === 'interaction' ? interactionErrors[item.data.action_id] : ''"
                :branch-disabled="branchDisabled"
                :branch-disabled-reason="branchDisabledReason"
                :branch-busy-event-id="branchBusyEventId"
                :editing="
                  Boolean(
                    editBranchItem &&
                    item.kind === 'user' &&
                    editBranchItem.sourceEventId === item.sourceEventId
                  )
                "
                :edit-busy="
                  Boolean(
                    editBranchItem &&
                    item.kind === 'user' &&
                    editBranchItem.sourceEventId === item.sourceEventId &&
                    branchBusyEventId === item.sourceEventId
                  )
                "
                @view-all-files="handleViewAllFiles"
                @file-click="handleFileClick"
                @tool-click="handleToolClick"
                @artifact-open="handleArtifactOpen"
                @retry-message="handleRetryMessage"
                @recover-failure="handleFailureRecovery"
                @resolve-interaction="handleResolveInteraction"
                @branch-action="handleBranchAction"
                @edit-submit="handleEditBranchSubmit"
                @edit-cancel="cancelEditBranch"
              />

              <div
                v-if="
                  (detail.session.value.status === 'running' ||
                    (hasInitialMessage && !initialMessageSent)) &&
                  !hasStreamingAssistantDraft
                "
                class="thinking-state"
              >
                <ThinkingIndicator />
              </div>
              <div
                v-if="runningStateLabel"
                class="conversation-status-note"
                :class="{ 'is-error': detail.error.value && detail.session.value, 'is-stopped': stoppedAt }"
                role="status"
                aria-live="polite"
              >
                {{ runningStateLabel }}
              </div>
              <div class="timeline-spacer" />
            </div>
          </div>

          <button
            v-if="showJumpToBottom"
            class="jump-to-bottom-button"
            type="button"
            @click="scrollToConversationBottom('smooth')"
          >
            <ArrowDown :size="14" />
            <span>跳到底部</span>
          </button>

          <div class="composer-shell">
            <PlanPanel :steps="planSteps" />
            <div
              v-if="detail.session.value.next_message"
              class="next-message-card"
              role="status"
              aria-live="polite"
            >
              <div class="next-message-copy">
                <strong>
                  {{
                    detail.session.value.next_message.state === 'processing'
                      ? '正在发送下一条'
                      : '下一条消息'
                  }}
                </strong>
                <span>{{ detail.session.value.next_message.message }}</span>
                <small v-if="detail.session.value.next_message.attachment_ids.length">
                  {{ detail.session.value.next_message.attachment_ids.length }} 个附件
                </small>
              </div>
              <button
                v-if="detail.session.value.next_message.state === 'queued'"
                class="next-message-cancel"
                type="button"
                @click="handleCancelNextMessage"
              >
                取消
              </button>
              <button
                v-if="
                  detail.session.value.status === 'completed' &&
                  detail.session.value.next_message.state === 'queued'
                "
                class="next-message-run"
                type="button"
                :disabled="queuedRunBusy"
                @click="handleRunNextMessage"
              >
                {{ queuedRunBusy ? '发送中' : '发送' }}
              </button>
            </div>
            <ChatInput
              :on-send="handleSend"
              :session-id="sessionId"
              :is-running="detail.session.value.status === 'running'"
              :disabled="
                isArchived ||
                pendingInteractionBlocksComposer ||
                (detail.session.value.status === 'completed' &&
                  Boolean(detail.session.value.next_message))
              "
              :on-stop="handleStop"
            />
          </div>
        </div>
      </section>

      <FilePreviewPanel
        v-if="previewFile"
        class="side-preview"
        :file="previewFile"
        @close="closePreview"
      />

      <ChatArtifactPreviewPanel
        v-if="previewArtifact"
        class="side-preview"
        :artifact="previewArtifact"
        @close="closePreview"
      />

      <ToolPreviewPanel
        v-if="resolvedPreviewTool"
        class="side-preview padded-preview"
        :tool="resolvedPreviewTool"
        @close="closePreview"
        @jump-to-latest="jumpToLatest"
        @open-vnc="vncOpen = true"
      />

      <TracePanel
        v-if="traceOpen"
        class="side-preview"
        :session-id="sessionId"
        @close="closePreview"
      />
    </div>

    <VNCOverlay v-if="vncOpen" :session-id="sessionId" @close="closeVNC" />
    <ArchivedSessionsDialog v-model:open="archivedDialogOpen" />
  </template>
</template>
