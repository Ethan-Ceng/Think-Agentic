<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{ draftId: string }>()
const router = useRouter()

function openDraft(): void {
  void router.push({ name: 'skills', query: { draft: props.draftId } })
}
</script>

<template>
  <button class="tool-open-draft" type="button" @click.stop="openDraft">打开草稿</button>
</template>
