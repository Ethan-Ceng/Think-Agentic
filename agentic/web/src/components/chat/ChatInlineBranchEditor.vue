<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { GitFork, Paperclip } from 'lucide-vue-next'
import SkillChip from '@/components/skills/SkillChip.vue'
import type { SkillRef } from '@/types/skill'

const props = withDefaults(defineProps<{
  content: string
  attachmentNames?: string[]
  skills?: SkillRef[]
  busy?: boolean
}>(), {
  attachmentNames: () => [],
  skills: () => [],
  busy: false,
})

const emit = defineEmits<{
  submit: [message: string]
  cancel: []
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const draft = ref('')
const trimmedDraft = computed(() => draft.value.trim())
const canSubmit = computed(
  () =>
    !props.busy &&
    Boolean(trimmedDraft.value) &&
    trimmedDraft.value.length <= 10000,
)

watch(
  () => props.content,
  content => {
    draft.value = content
  },
  { immediate: true },
)

onMounted(() => {
  void nextTick(() => {
    textareaRef.value?.focus()
    textareaRef.value?.setSelectionRange(
      textareaRef.value.value.length,
      textareaRef.value.value.length,
    )
  })
})

function submit() {
  if (!canSubmit.value) return
  emit('submit', trimmedDraft.value)
}

function cancel() {
  if (props.busy) return
  emit('cancel')
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    cancel()
    return
  }
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="chat-inline-branch-editor" aria-label="编辑消息并创建分支">
    <div class="branch-edit-notice">
      <GitFork :size="16" aria-hidden="true" />
      <span>原对话不会改变；提交后会从这条消息创建新分支并继续执行。</span>
    </div>

    <label class="branch-edit-field">
      <span>消息内容</span>
      <textarea
        ref="textareaRef"
        v-model="draft"
        rows="5"
        maxlength="10000"
        :disabled="busy"
        aria-label="编辑后的消息内容"
        @keydown="handleKeydown"
      />
    </label>

    <div v-if="attachmentNames.length" class="branch-edit-readonly">
      <span><Paperclip :size="14" aria-hidden="true" />沿用附件</span>
      <div class="branch-edit-tags">
        <span
          v-for="name in attachmentNames"
          :key="name"
          class="branch-edit-attachment"
        >
          {{ name }}
        </span>
      </div>
    </div>

    <div v-if="skills.length" class="branch-edit-readonly">
      <span>沿用 Skills</span>
      <div class="branch-edit-tags">
        <SkillChip
          v-for="skill in skills"
          :key="`${skill.source}:${skill.skill_id ?? skill.name}`"
          :skill="skill"
        />
      </div>
    </div>

    <div class="chat-inline-branch-editor-footer">
      <span class="branch-edit-character-count">
        {{ draft.length }} / 10000
      </span>
      <div class="chat-inline-branch-editor-actions">
        <button
          type="button"
          data-action="cancel"
          :disabled="busy"
          @click="cancel"
        >
          取消
        </button>
        <button
          class="is-primary"
          type="button"
          data-action="submit"
          :disabled="!canSubmit"
          @click="submit"
        >
          {{ busy ? '正在创建…' : '创建分支并发送' }}
        </button>
      </div>
    </div>
  </div>
</template>
