<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { Sparkles, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { sessionApi } from '@/lib/api/session'

const props = withDefaults(defineProps<{
  open: boolean
  initialGoal?: string
}>(), { initialGoal: '' })
const emit = defineEmits<{ close: [] }>()
const router = useRouter()
const form = reactive({ goal: props.initialGoal, examples: '', resources: '' })
const busy = ref(false)
const error = ref('')

watch(() => props.initialGoal, (value) => { form.goal = value })

function buildMessage(): string {
  const examples = form.examples.trim() || 'No examples supplied; ask if examples would change the design.'
  const resources = form.resources.trim() || 'No required resources supplied.'
  return [
    'Create a standard reusable Agent Skill with me. Do not publish it.',
    `Goal:\n${form.goal.trim()}`,
    `Representative requests or examples:\n${examples}`,
    `Required resources, tools, or constraints:\n${resources}`,
    'Use the isolated draft tools, validate and revise the package, then hand me the draft ID for review.',
  ].join('\n\n')
}

async function start(): Promise<void> {
  if (!form.goal.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const launch = await sessionApi.createSessionWithInitialMessage({
      message: buildMessage(),
      attachmentIds: [],
      skills: [{ source: 'bundled', skill_id: null, name: 'skill-creator' }],
    })
    emit('close')
    await router.push(`/sessions/${launch.sessionId}?init=${launch.init}`)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Unable to start Skill Creator'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="open" class="creator-backdrop" role="presentation" @click.self="emit('close')">
    <section class="creator-dialog" role="dialog" aria-modal="true" aria-labelledby="creator-title">
      <header>
        <span class="creator-icon"><Sparkles :size="18" /></span>
        <div><h2 id="creator-title">用 AI 创建 Skill</h2><p>Creator 会准备并校验草稿；发布仍由你审阅后完成。</p></div>
        <button type="button" aria-label="关闭" @click="emit('close')"><X :size="17" /></button>
      </header>
      <form @submit.prevent="start">
        <label>目标 <textarea v-model="form.goal" data-testid="creator-goal" required placeholder="这个 Skill 要稳定完成什么？" /></label>
        <label>示例请求 <textarea v-model="form.examples" data-testid="creator-examples" placeholder="每行一个典型请求或期望结果" /></label>
        <label>必需资源与约束 <textarea v-model="form.resources" data-testid="creator-resources" placeholder="参考资料、脚本、工具、环境或非目标" /></label>
        <p v-if="error" class="creator-error">{{ error }}</p>
        <footer><button type="button" @click="emit('close')">取消</button><button class="primary" data-testid="start-creator" type="submit" :disabled="busy || !form.goal.trim()">{{ busy ? '正在创建对话…' : '开始创建' }}</button></footer>
      </form>
    </section>
  </div>
</template>

<style scoped>
.creator-backdrop { position: fixed; z-index: 90; inset: 0; display: grid; place-items: center; padding: 20px; background: rgb(0 0 0 / 45%); }
.creator-dialog { width: min(640px, 100%); padding: 20px; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--surface-primary); box-shadow: 0 18px 60px rgb(0 0 0 / 24%); }
header { display: flex; align-items: flex-start; gap: 10px; }
header > div { flex: 1; } h2, p { margin: 0; } header p { margin-top: 4px; color: var(--text-secondary); font-size: 13px; }
.creator-icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 9px; background: var(--accent-soft); color: var(--accent-primary); }
form { display: grid; gap: 13px; margin-top: 18px; } label { display: grid; gap: 6px; color: var(--text-secondary); font-size: 13px; }
textarea { min-height: 76px; padding: 10px; border: 1px solid var(--border-light); border-radius: 7px; resize: vertical; background: var(--surface-primary); color: var(--text-primary); }
footer { display: flex; justify-content: flex-end; gap: 8px; } button { min-height: 36px; padding: 0 11px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; }
button.primary { border-color: var(--accent-primary); background: var(--accent-primary); color: var(--accent-contrast); } button:disabled { opacity: .5; cursor: not-allowed; }
.creator-error { color: var(--status-error); font-size: 12px; }
</style>
