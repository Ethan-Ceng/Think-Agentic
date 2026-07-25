<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  content: string
  title: string
  maxContentBytes?: number
}>(), {
  maxContentBytes: 500_000,
})

const CONTENT_SECURITY_POLICY = [
  "default-src 'none'",
  "script-src 'none'",
  "connect-src 'none'",
  "worker-src 'none'",
  "child-src 'none'",
  "navigate-to 'none'",
  "img-src data: blob:",
  "style-src 'unsafe-inline'",
  "font-src data:",
  "media-src data: blob:",
  "form-action 'none'",
  "base-uri 'none'",
  "object-src 'none'",
  "frame-src 'none'",
].join('; ')

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[character] ?? character,
  )
}

const contentBytes = computed(() => new TextEncoder().encode(props.content).byteLength)
const tooLarge = computed(() => contentBytes.value > props.maxContentBytes)
const safeDocument = computed(() => [
  '<!doctype html><html><head>',
  '<meta charset="utf-8">',
  `<meta http-equiv="Content-Security-Policy" content="${CONTENT_SECURITY_POLICY}">`,
  '<meta name="referrer" content="no-referrer">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  `<title>${escapeHtml(props.title)}</title>`,
  '</head><body>',
  props.content,
  '</body></html>',
].join(''))
</script>

<template>
  <div class="safe-html-preview">
    <div v-if="tooLarge" class="artifact-preview-limit" role="status">
      <strong>内容过大，无法安全预览</strong>
      <span>请查看源码或下载文件后打开。</span>
    </div>
    <iframe
      v-else
      sandbox=""
      referrerpolicy="no-referrer"
      :title="`${title} 安全预览`"
      :srcdoc="safeDocument"
    />
  </div>
</template>
