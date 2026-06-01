<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'

const props = defineProps<{
  content: string
}>()

const CJK_RANGES = '\\u3000-\\u303F\\u4E00-\\u9FFF\\uFF01-\\uFF60'
const URL_FOLLOWED_BY_CJK = new RegExp(
  `(https?:\\/\\/[^\\s${CJK_RANGES}]+)([${CJK_RANGES}])`,
  'g',
)

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

function normalizeAutolinks(text: string): string {
  return text.replace(URL_FOLLOWED_BY_CJK, '$1 $2')
}

const html = computed(() => md.render(normalizeAutolinks(props.content || '')))
</script>

<template>
  <div class="markdown-content" v-html="html" />
</template>
