<script setup lang="ts">
import { computed } from 'vue'
import { CircuitBoard, Loader2, MoreHorizontal, Trash } from 'lucide-vue-next'
import type { Session } from '@/lib/api/types'
import { formatRelativeDate } from '@/lib/utils'

const props = defineProps<{
  session: Session
  active: boolean
}>()

const emit = defineEmits<{
  open: [sessionId: string]
  delete: [session: Session]
}>()

const description = computed(() => props.session.latest_message || '暂无消息')
const dateLabel = computed(() => formatRelativeDate(props.session.latest_message_at))
const isRunning = computed(
  () => props.session.status === 'running' || props.session.status === 'waiting',
)

function handleCommand(command: string | number | object) {
  if (command === 'delete') {
    emit('delete', props.session)
  }
}
</script>

<template>
  <article
    class="session-item"
    :class="{ active }"
    role="button"
    tabindex="0"
    @click="emit('open', session.session_id)"
    @keydown.enter.prevent="emit('open', session.session_id)"
    @keydown.space.prevent="emit('open', session.session_id)"
  >
    <div class="item-avatar">
      <Loader2 v-if="isRunning" :size="16" class="spin" />
      <CircuitBoard v-else :size="16" />
    </div>

    <div class="session-item-main">
      <p class="session-title">{{ session.title || '新任务' }}</p>
      <p class="session-desc">{{ description }}</p>
    </div>

    <div class="session-item-actions" @click.stop>
      <span>{{ dateLabel }}</span>
      <ElDropdown
        trigger="click"
        placement="bottom-end"
        popper-class="session-action-dropdown"
        teleported
        @command="handleCommand"
      >
        <button
          class="icon-button subtle tiny"
          type="button"
          aria-label="更多操作"
          @click.stop
        >
          <MoreHorizontal :size="16" />
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="delete" class="session-action-dropdown-item danger">
              <Trash :size="14" />
              <span>删除</span>
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>
    </div>
  </article>
</template>
