<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { GitFork, Paperclip } from 'lucide-vue-next'
import SkillChip from '@/components/skills/SkillChip.vue'
import type { SkillRef } from '@/types/skill'

const props = withDefaults(defineProps<{
  open: boolean
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
  'update:open': [open: boolean]
  submit: [message: string]
}>()

const draft = ref('')
const dialogOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
})
const canSubmit = computed(() => Boolean(draft.value.trim()) && !props.busy)

watch(
  () => props.open,
  (open) => {
    if (open) draft.value = props.content
  },
  { immediate: true },
)

function submit() {
  const message = draft.value.trim()
  if (!message || props.busy) return
  emit('submit', message)
}
</script>

<template>
  <ElDialog
    v-model="dialogOpen"
    title="编辑并在新分支重新提交"
    width="min(560px, calc(100vw - 32px))"
    append-to-body
    destroy-on-close
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
  >
    <div class="branch-edit-dialog">
      <div class="branch-edit-notice">
        <GitFork :size="17" />
        <span>原对话不会改变；系统会复制此前可见内容，并从这条消息重新执行。</span>
      </div>
      <label class="branch-edit-field">
        <span>消息内容</span>
        <ElInput
          v-model="draft"
          type="textarea"
          :rows="6"
          maxlength="10000"
          show-word-limit
          resize="vertical"
          autofocus
          aria-label="编辑后的消息内容"
          @keydown.ctrl.enter.prevent="submit"
          @keydown.meta.enter.prevent="submit"
        />
      </label>
      <div v-if="attachmentNames.length" class="branch-edit-readonly">
        <span><Paperclip :size="14" />沿用附件</span>
        <div class="branch-edit-tags">
          <ElTag v-for="name in attachmentNames" :key="name" size="small">
            {{ name }}
          </ElTag>
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
    </div>
    <template #footer>
      <ElButton :disabled="busy" @click="dialogOpen = false">取消</ElButton>
      <ElButton type="primary" :loading="busy" :disabled="!canSubmit" @click="submit">
        创建分支并发送
      </ElButton>
    </template>
  </ElDialog>
</template>
