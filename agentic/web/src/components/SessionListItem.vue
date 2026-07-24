<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  Archive,
  Check,
  CircuitBoard,
  Loader2,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Trash,
  X,
} from 'lucide-vue-next'
import type { Session } from '@/lib/api/types'
import { formatRelativeDate } from '@/lib/utils'

const props = withDefaults(defineProps<{
  session: Session
  active: boolean
  busy?: boolean
}>(), {
  busy: false,
})

const emit = defineEmits<{
  open: [sessionId: string]
  rename: [session: Session, title: string]
  togglePin: [session: Session]
  archive: [session: Session]
  delete: [session: Session]
}>()

const renaming = ref(false)
const titleInput = ref('')
const submittedTitle = ref('')
const titleInputRef = ref<HTMLInputElement | null>(null)

const description = computed(() => props.session.latest_message || '暂无消息')
const dateLabel = computed(() => formatRelativeDate(props.session.latest_message_at))
const isRunning = computed(
  () => props.session.status === 'running' || props.session.status === 'waiting',
)
const archiveReason = computed(() => {
  if (props.session.status === 'running') return '任务运行中，完成或停止后才能归档'
  if (props.session.status === 'waiting') return '任务正在等待交互，处理后才能归档'
  if (props.session.has_next_message) return '存在排队消息，发送或取消后才能归档'
  return ''
})
const archiveDisabled = computed(() => Boolean(archiveReason.value))

watch(
  () => props.session.title,
  (title) => {
    if (renaming.value && submittedTitle.value && title === submittedTitle.value) {
      cancelRename()
    }
  },
)

function openSession() {
  if (!renaming.value) emit('open', props.session.session_id)
}

async function beginRename() {
  if (props.busy) return
  renaming.value = true
  submittedTitle.value = ''
  titleInput.value = props.session.title || '新任务'
  await nextTick()
  titleInputRef.value?.focus()
  titleInputRef.value?.select()
}

function cancelRename() {
  renaming.value = false
  submittedTitle.value = ''
  titleInput.value = ''
}

function submitRename() {
  const title = titleInput.value.trim()
  if (!title || props.busy) return
  if (title === props.session.title) {
    cancelRename()
    return
  }
  submittedTitle.value = title
  emit('rename', props.session, title)
}

function handleCommand(command: string | number | object) {
  if (command === 'rename') void beginRename()
  else if (command === 'pin') emit('togglePin', props.session)
  else if (command === 'archive' && !archiveDisabled.value) emit('archive', props.session)
  else if (command === 'delete') emit('delete', props.session)
}
</script>

<template>
  <article
    class="session-item"
    :class="{ active, renaming }"
    role="button"
    :tabindex="renaming ? -1 : 0"
    :aria-current="active ? 'page' : undefined"
    @click="openSession"
    @keydown.enter.prevent="openSession"
    @keydown.space.prevent="openSession"
  >
    <div class="item-avatar">
      <Loader2 v-if="isRunning" :size="16" class="spin" />
      <CircuitBoard v-else :size="16" />
    </div>

    <form
      v-if="renaming"
      class="session-rename-form"
      aria-label="重命名任务"
      @click.stop
      @submit.prevent="submitRename"
    >
      <input
        ref="titleInputRef"
        v-model="titleInput"
        maxlength="100"
        aria-label="新的任务标题"
        :disabled="busy"
        @keydown.enter.prevent="submitRename"
        @keydown.esc.prevent="cancelRename"
      />
      <button
        type="button"
        class="icon-button subtle tiny"
        aria-label="取消重命名"
        :disabled="busy"
        @click="cancelRename"
      >
        <X :size="14" />
      </button>
      <button
        type="submit"
        class="icon-button subtle tiny"
        aria-label="保存任务标题"
        :disabled="busy || !titleInput.trim()"
      >
        <Loader2 v-if="busy" :size="14" class="spin" />
        <Check v-else :size="14" />
      </button>
    </form>

    <div v-else class="session-item-main">
      <p class="session-title">
        <span>{{ session.title || '新任务' }}</span>
        <Pin v-if="session.is_pinned" :size="12" aria-label="已置顶" />
      </p>
      <p class="session-desc">{{ description }}</p>
    </div>

    <div v-if="!renaming" class="session-item-actions" @click.stop>
      <span>{{ dateLabel }}</span>
      <ElDropdown
        trigger="click"
        placement="bottom-end"
        popper-class="session-action-dropdown"
        teleported
        :disabled="busy"
        @command="handleCommand"
      >
        <button
          class="icon-button subtle tiny"
          type="button"
          :aria-label="`更多操作：${session.title || '新任务'}`"
          :disabled="busy"
          @click.stop
        >
          <Loader2 v-if="busy" :size="16" class="spin" />
          <MoreHorizontal v-else :size="16" />
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="rename" class="session-action-dropdown-item">
              <Pencil :size="14" />
              <span>重命名</span>
            </ElDropdownItem>
            <ElDropdownItem command="pin" class="session-action-dropdown-item">
              <PinOff v-if="session.is_pinned" :size="14" />
              <Pin v-else :size="14" />
              <span>{{ session.is_pinned ? '取消置顶' : '置顶' }}</span>
            </ElDropdownItem>
            <ElDropdownItem
              command="archive"
              class="session-action-dropdown-item"
              :disabled="archiveDisabled"
              :title="archiveReason || '归档任务'"
            >
              <Archive :size="14" />
              <span>归档</span>
            </ElDropdownItem>
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
