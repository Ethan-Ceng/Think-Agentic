<script setup lang="ts">
import { FileSearch, FileText } from 'lucide-vue-next'
import type { AttachmentFile } from '@/lib/session-events'
import { formatFileSize } from '@/lib/utils'

defineProps<{
  role: 'user' | 'assistant'
  files: AttachmentFile[]
  showViewAll?: boolean
}>()

const emit = defineEmits<{
  fileClick: [file: AttachmentFile]
  viewAllFiles: []
}>()

function sizeLabel(file: AttachmentFile): string {
  return file.sizeLabel ?? formatFileSize(file.size)
}
</script>

<template>
  <div class="attachments-message" :class="`role-${role}`">
    <div class="attachment-wrap">
      <article
        v-for="file in files"
        :key="`${file.id}-${file.filename}`"
        class="attachment-card"
        role="button"
        tabindex="0"
        @click="emit('fileClick', file)"
        @keydown.enter.prevent="emit('fileClick', file)"
        @keydown.space.prevent="emit('fileClick', file)"
      >
        <div class="file-icon">
          <FileText :size="18" />
        </div>
        <div class="attachment-info">
          <p>{{ file.filename }}</p>
          <span>{{ file.extension }} · {{ sizeLabel(file) }}</span>
        </div>
      </article>

      <button
        v-if="showViewAll"
        type="button"
        class="attachment-card view-all-files"
        @click="emit('viewAllFiles')"
      >
        <div class="file-icon neutral">
          <FileSearch :size="18" />
        </div>
        <span>查看此任务中的所有文件</span>
      </button>
    </div>
  </div>
</template>
