<script setup lang="ts">
import AttachmentsMessage from '@/components/chat/AttachmentsMessage.vue'
import MarkdownContent from '@/components/MarkdownContent.vue'
import AssistantAvatar from '@/components/chat/AssistantAvatar.vue'
import MessageActions from '@/components/chat/MessageActions.vue'
import ThinkingBlock from '@/components/chat/ThinkingBlock.vue'
import ToolCallCard from '@/components/chat/ToolCallCard.vue'
import InteractionCard from '@/components/chat/InteractionCard.vue'
import SkillChip from '@/components/skills/SkillChip.vue'
import {
  AlertCircle,
  CheckCircle2,
  CircleStop,
  Loader2,
  MessageSquareOff,
  RefreshCw,
} from 'lucide-vue-next'
import type { Component } from 'vue'
import type { ResolveInteractionParams, ResumeMode, ToolEvent } from '@/lib/api/types'
import type { AttachmentFile, TimelineItem, UserMessageStatus } from '@/lib/session-events'
import { getFriendlyToolLabel, getToolKind } from '@/lib/tool-utils'

defineProps<{
  item: TimelineItem
  domId?: string
  showRecoveryActions?: boolean
  recoveryBusy?: boolean
  interactionBusy?: boolean
  interactionError?: string
}>()

const emit = defineEmits<{
  viewAllFiles: []
  fileClick: [file: AttachmentFile]
  toolClick: [tool: ToolEvent]
  retryMessage: [itemId: string]
  recoverTask: [mode: ResumeMode]
  resolveInteraction: [actionId: string, params: ResolveInteractionParams]
}>()

const statusIconMap: Record<UserMessageStatus, Component> = {
  sending: Loader2,
  sent: CheckCircle2,
  failed: AlertCircle,
  stopped: CircleStop,
}

const friendlyReplyError = '模型服务暂时不可用。请检查模型配置、账户余额或网络连接后重试。'

function getUserStatus(item: TimelineItem): UserMessageStatus {
  return item.kind === 'user' && item.status ? item.status : 'sent'
}

function getUserStatusLabel(item: TimelineItem): string {
  if (item.kind !== 'user') return ''
  if (item.statusText) return item.statusText

  switch (getUserStatus(item)) {
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

function getUserStatusIcon(item: TimelineItem): Component {
  return statusIconMap[getUserStatus(item)]
}

function isAssistantEmpty(item: TimelineItem): boolean {
  return (
    item.kind === 'assistant' &&
    !(item.data.message ?? '').trim() &&
    !item.data.attachments?.length
  )
}

function handleToolClick(tool: ToolEvent) {
  if (getToolKind(tool) === 'message') return
  emit('toolClick', tool)
}

function handleResolveInteraction(actionId: string, params: ResolveInteractionParams) {
  emit('resolveInteraction', actionId, params)
}
</script>

<template>
  <article v-if="item.kind === 'user'" :id="domId" class="chat-message chat-message-user" aria-label="你的消息">
    <div class="message-stack user-stack">
      <div class="message-bubble user-bubble" :class="`status-${getUserStatus(item)}`">
        <p class="message-text">{{ item.data.message ?? '' }}</p>
      </div>
      <div v-if="item.data.skills?.length" class="message-skill-chips">
        <SkillChip v-for="skill in item.data.skills" :key="`${skill.source}:${skill.skill_id ?? skill.name}`" :skill="skill" />
      </div>
      <div class="user-message-meta" :class="`status-${getUserStatus(item)}`">
        <span v-if="item.timeLabel">{{ item.timeLabel }}</span>
        <span class="message-status-pill">
          <component
            :is="getUserStatusIcon(item)"
            :size="12"
            :class="{ spin: getUserStatus(item) === 'sending' }"
          />
          {{ getUserStatusLabel(item) }}
        </span>
        <button
          v-if="item.canRetry"
          class="message-retry-button"
          type="button"
          @click="emit('retryMessage', item.id)"
        >
          <RefreshCw :size="12" />
          <span>重试</span>
        </button>
      </div>
      <p v-if="item.errorText" class="message-error-text">{{ item.errorText }}</p>
      <MessageActions :content="item.data.message ?? ''" align="right" />
    </div>
  </article>

  <article v-else-if="item.kind === 'assistant'" :id="domId" class="chat-message chat-message-assistant" aria-label="MoocManus 回复">
    <AssistantAvatar />
    <div class="assistant-message-body">
      <div class="assistant-message-header">
        <strong>MoocManus</strong>
        <span>{{ item.timeLabel || 'AI Assistant' }}</span>
      </div>
      <MarkdownContent v-if="!isAssistantEmpty(item)" :content="item.data.message ?? ''" />
      <div v-else class="assistant-status-card assistant-empty-card">
        <MessageSquareOff :size="16" />
        <div>
          <strong>Assistant 返回了空回复</strong>
          <span>没有可展示的消息内容</span>
        </div>
      </div>
      <MessageActions v-if="!isAssistantEmpty(item)" :content="item.data.message ?? ''" />
    </div>
  </article>

  <div v-else-if="item.kind === 'tool'" class="timeline-tool-row">
    <div v-if="getToolKind(item.data) === 'message'" class="message-tool-note">
      {{ getFriendlyToolLabel(item.data) }}
    </div>
    <ToolCallCard
      v-else
      :data="item.data"
      :time-label="item.timeLabel || '刚刚'"
      clickable
      @click="handleToolClick"
    />
  </div>

  <ThinkingBlock
    v-else-if="item.kind === 'step'"
    :id="domId"
    :step="item.data"
    :tools="item.tools"
    @tool-click="handleToolClick"
  />

  <InteractionCard
    v-else-if="item.kind === 'interaction'"
    :interaction="item.data"
    :busy="interactionBusy"
    :error="interactionError"
    @resolve="handleResolveInteraction"
  />

  <AttachmentsMessage
    v-else-if="item.kind === 'attachments'"
    :role="item.role"
    :files="item.files"
    :show-view-all="item.role === 'assistant'"
    @file-click="emit('fileClick', $event)"
    @view-all-files="emit('viewAllFiles')"
  />

  <article v-else-if="item.kind === 'error'" :id="domId" class="chat-message chat-message-assistant error-message" role="alert">
    <AssistantAvatar />
    <div class="assistant-message-body">
      <div class="assistant-message-header">
        <strong>MoocManus</strong>
        <span>{{ item.timeLabel || '错误' }}</span>
      </div>
      <div class="assistant-status-card assistant-error-card">
        <div class="assistant-status-card-title">
          <AlertCircle :size="16" />
          <strong>本次回复未完成</strong>
        </div>
        <MarkdownContent :content="friendlyReplyError" />
        <div v-if="showRecoveryActions" class="task-recovery-actions">
          <button
            class="task-recovery-button is-primary"
            type="button"
            :disabled="recoveryBusy"
            @click="emit('recoverTask', 'continue')"
          >
            重新生成回复
          </button>
          <button
            class="task-recovery-button"
            type="button"
            :disabled="recoveryBusy"
            @click="emit('recoverTask', 'restart')"
          >
            重新执行任务
          </button>
        </div>
      </div>
    </div>
  </article>
</template>
