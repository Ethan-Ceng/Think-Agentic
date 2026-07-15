<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown } from 'lucide-vue-next'
import { ElMessageBox } from 'element-plus'
import ChatInput from '@/components/chat/ChatInput.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import PlanPanel from '@/components/chat/PlanPanel.vue'
import ThinkingIndicator from '@/components/chat/ThinkingIndicator.vue'
import SessionHeader from '@/components/SessionHeader.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiState from '@/components/ui/UiState.vue'
import { useSessionDetail } from '@/composables/useSessionDetail'
import { useToast } from '@/composables/useToast'
import { sessionApi } from '@/lib/api/session'
import type { FileInfo, ResumeMode, ToolEvent } from '@/lib/api/types'
import type { AttachmentFile, TimelineItem, UserMessageStatus } from '@/lib/session-events'
import { eventsToTimeline, formatMessageTimeLabel, getLatestPlanFromEvents } from '@/lib/session-events'
import { getToolKind } from '@/lib/tool-utils'

const props = withDefaults(defineProps<{
  sessionId: string
  initialMessage?: string
  initialAttachments?: string[]
  hasInitialMessage?: boolean
}>(), {
  initialMessage: undefined,
  initialAttachments: () => [],
  hasInitialMessage: false,
})

type PendingUserMessage = {
  id: string
  message: string
  attachmentIds: string[]
  files: AttachmentFile[]
  createdAt: number
  status: Exclude<UserMessageStatus, 'sent'>
  errorText?: string
}

const router = useRouter()
const route = useRoute()
const toast = useToast()
const FilePreviewPanel = defineAsyncComponent(() => import('@/components/FilePreviewPanel.vue'))
const TracePanel = defineAsyncComponent(() => import('@/components/TracePanel.vue'))
const ToolPreviewPanel = defineAsyncComponent(() => import('@/components/chat/ToolPreviewPanel.vue'))
const VNCOverlay = defineAsyncComponent(() => import('@/components/VNCOverlay.vue'))
const fileListOpen = ref(false)
const previewFile = ref<AttachmentFile | null>(null)
const previewTool = ref<ToolEvent | null>(null)
const traceOpen = ref(false)
const vncOpen = ref(false)
const initialMessageSent = ref(false)
const scrollContainerRef = ref<HTMLDivElement | null>(null)
const prevToolCount = ref(0)
const isNearBottom = ref(true)
const pendingUserMessage = ref<PendingUserMessage | null>(null)
const stoppedAt = ref<number | null>(null)
const lastFocusedEvent = ref('')
let focusTimer = 0

const detail = useSessionDetail(
  computed(() => props.sessionId),
  computed(() => props.hasInitialMessage),
)

const baseTimeline = computed(() => eventsToTimeline(detail.events.value))
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
const latestRecoverableErrorId = computed(() => {
  if (detail.session.value?.status !== 'completed') return null
  for (let i = timeline.value.length - 1; i >= 0; i--) {
    if (timeline.value[i].kind === 'error') return timeline.value[i].id
  }
  return null
})
const hasPreview = computed(() => previewFile.value !== null || resolvedPreviewTool.value !== null || traceOpen.value)
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
    return '等待你的回复'
  }
  if (detail.session.value?.status === 'running') {
    return '正在生成回复'
  }
  return ''
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

function fileInfoToAttachment(file: FileInfo): AttachmentFile {
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
): PendingUserMessage {
  return {
    id: `pending-${Date.now()}`,
    message,
    attachmentIds,
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
  pendingUserMessage.value = {
    ...pending,
    status: 'sending',
    errorText: undefined,
  }

  try {
    await detail.sendMessage(pending.message, pending.attachmentIds)
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

    if (toolCount > prevToolCount.value && latestTool) {
      const shouldFollow = isNearBottom.value
      previewTool.value = latestTool
      previewFile.value = null
      traceOpen.value = false
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
      !detail.loading.value &&
      !detail.streaming.value
    ) {
      initialMessageSent.value = true
      const pending = createPendingMessage(props.initialMessage, props.initialAttachments || [])
      pendingUserMessage.value = pending
      stoppedAt.value = null
      isNearBottom.value = true
      scrollToConversationBottom('auto')

      detail
        .sendMessage(pending.message, pending.attachmentIds)
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
    const pending = pendingUserMessage.value
    if (!pending) return
    if (hasMatchingUserMessage(items, pending)) {
      pendingUserMessage.value = null
    }
  },
)

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
    pendingUserMessage.value = null
    stoppedAt.value = null
    isNearBottom.value = true
    lastFocusedEvent.value = ''
    scrollToConversationBottom('auto')
  },
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

onBeforeUnmount(() => window.clearTimeout(focusTimer))

async function handleSend(message: string, uploadedFiles: FileInfo[]) {
  const pending = createPendingMessage(
    message,
    uploadedFiles.map((file) => file.id),
    uploadedFiles.map(fileInfoToAttachment),
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
  previewFile.value = file
  previewTool.value = null
  traceOpen.value = false
}

async function handleRecoverTask(mode: ResumeMode) {
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

function handleToolClick(tool: ToolEvent) {
  if (getToolKind(tool) === 'message') return
  previewTool.value = tool
  previewFile.value = null
  traceOpen.value = false
}

function closePreview() {
  previewFile.value = null
  previewTool.value = null
}

function openTracePanel() {
  traceOpen.value = true
  previewFile.value = null
  previewTool.value = null
}

function jumpToLatest() {
  const latest = findLatestTool(timeline.value)
  if (latest) {
    previewTool.value = latest
    previewFile.value = null
    traceOpen.value = false
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
  if (latest && detail.session.value?.status === 'running') {
    previewTool.value = latest
    previewFile.value = null
    traceOpen.value = false
    window.setTimeout(() => {
      scrollContainerRef.value?.scrollTo({
        top: scrollContainerRef.value.scrollHeight,
        behavior: 'smooth',
      })
    }, 100)
  }
}

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
                :show-recovery-actions="item.kind === 'error' && item.id === latestRecoverableErrorId"
                :recovery-busy="detail.streaming.value"
                @view-all-files="handleViewAllFiles"
                @file-click="handleFileClick"
                @tool-click="handleToolClick"
                @retry-message="handleRetryMessage"
                @recover-task="handleRecoverTask"
              />

              <div
                v-if="detail.session.value.status === 'running' || (hasInitialMessage && !initialMessageSent)"
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
            <ChatInput
              :on-send="handleSend"
              :session-id="sessionId"
              :is-running="detail.session.value.status === 'running'"
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
        @close="traceOpen = false"
      />
    </div>

    <VNCOverlay v-if="vncOpen" :session-id="sessionId" @close="closeVNC" />
  </template>
</template>
