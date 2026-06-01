<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import {
  AlertCircle,
  Bot,
  Braces,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  ExternalLink,
  FileSearch,
  Globe,
  Monitor,
  Play,
  Search,
  Sparkles,
  SquareChevronRight,
  Terminal,
  Wrench,
  X,
} from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import type { ToolEvent } from '@/lib/api/types'
import {
  getArg,
  getToolFailureMessage,
  getFriendlyToolLabel,
  getToolKind,
  getToolResultText,
  isToolFailed,
  stringifyToolValue,
  type ToolKind,
} from '@/lib/tool-utils'

type ConsoleRecord = { ps1: string; command: string; output: string }
type SearchResultItem = { url: string; title: string; snippet: string }

const props = defineProps<{
  tool: ToolEvent
}>()

const emit = defineEmits<{
  close: []
  jumpToLatest: []
  openVnc: []
}>()

const toast = useToast()
const copiedTarget = ref<'args' | 'result' | null>(null)
const kind = computed(() => getToolKind(props.tool))
const label = computed(() => getFriendlyToolLabel(props.tool))
const isRunning = computed(() => props.tool.status === 'calling')
const isFailed = computed(() => isToolFailed(props.tool))
const statusLabel = computed(() => (isRunning.value ? '运行中' : isFailed.value ? '失败' : '已完成'))
const statusType = computed(() => (isRunning.value ? 'warning' : isFailed.value ? 'danger' : 'success'))
const failureMessage = computed(() => getToolFailureMessage(props.tool))

const content = computed<Record<string, unknown> | null>(() => {
  const value = props.tool.content
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
})

const iconMap: Record<ToolKind, Component> = {
  bash: Terminal,
  browser: Globe,
  search: Search,
  file: FileSearch,
  mcp: Wrench,
  a2a: Bot,
  message: Monitor,
  default: SquareChevronRight,
}

const toolDescriptionMap: Record<ToolKind, string> = {
  bash: '终端',
  browser: '浏览器',
  search: '搜索',
  file: '文件',
  mcp: 'MCP 服务',
  a2a: 'A2A 智能体',
  message: '消息',
  default: '工具',
}

const consoleRecords = computed<ConsoleRecord[]>(() => {
  const consoleData = content.value?.console
  return Array.isArray(consoleData) ? (consoleData as ConsoleRecord[]) : []
})

const searchResults = computed<SearchResultItem[]>(() => {
  const results = content.value?.results
  return Array.isArray(results) ? (results as SearchResultItem[]) : []
})

const screenshot = computed(() =>
  typeof content.value?.screenshot === 'string' ? content.value.screenshot : '',
)
const fileContent = computed(() =>
  typeof content.value?.content === 'string' ? content.value.content : '',
)
const resultContent = computed(() => {
  const result = kind.value === 'a2a' ? content.value?.a2a_result : content.value?.result
  if (result == null) return ''
  return typeof result === 'string' ? result : JSON.stringify(result, null, 2)
})
const genericContent = computed(() => {
  if (props.tool.content == null) return ''
  return typeof props.tool.content === 'string'
    ? props.tool.content
    : JSON.stringify(props.tool.content, null, 2)
})
const argsContent = computed(() =>
  Object.keys(props.tool.args || {}).length > 0
    ? JSON.stringify(props.tool.args, null, 2)
    : '',
)
const argsCopyText = computed(() => stringifyToolValue(props.tool.args || {}))
const resultCopyText = computed(() => getToolResultText(props.tool))

const sessionId = computed(() => getArg(props.tool.args, 'session_id'))
const url = computed(() => getArg(props.tool.args, 'url', 'href', 'link'))
const filepath = computed(() => getArg(props.tool.args, 'filepath', 'path', 'pathname'))
const query = computed(() => getArg(props.tool.args, 'query', 'q', 'message', 'input'))
const command = computed(() => getArg(props.tool.args, 'command', 'cmd', 'script', 'input'))

const detailRows = computed(() => [
  { label: '类型', value: toolDescriptionMap[kind.value] },
  { label: '函数', value: props.tool.function || props.tool.name || 'tool' },
  ...(sessionId.value ? [{ label: '会话', value: sessionId.value }] : []),
  ...(filepath.value ? [{ label: '路径', value: filepath.value }] : []),
  ...(url.value ? [{ label: '地址', value: url.value }] : []),
  ...(query.value ? [{ label: '查询', value: query.value }] : []),
])

async function copyText(text: string, target: 'args' | 'result') {
  if (!text.trim()) return

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }

    copiedTarget.value = target
    toast.success(target === 'args' ? '已复制参数' : '已复制结果')
    window.setTimeout(() => {
      if (copiedTarget.value === target) copiedTarget.value = null
    }, 1400)
  } catch {
    toast.error('复制失败')
  }
}
</script>

<template>
  <aside class="preview-panel tool-preview">
    <header class="tool-preview-hero">
      <span class="tool-preview-icon" :class="`kind-${kind}`">
        <component :is="iconMap[kind]" :size="18" />
      </span>

      <div class="tool-preview-title">
        <p>
          <Monitor :size="14" />
          <span>工具执行详情</span>
          <ElTag size="small" round effect="light" :type="statusType">
            {{ statusLabel }}
          </ElTag>
        </p>
        <h2 :title="label">{{ label }}</h2>
        <span>{{ toolDescriptionMap[kind] }} · {{ tool.function || tool.name || 'tool' }}</span>
      </div>

      <div class="tool-preview-actions">
        <ElTooltip :content="copiedTarget === 'args' ? '已复制参数' : '复制参数'" placement="bottom">
          <button
            class="icon-button subtle tiny"
            type="button"
            aria-label="复制工具参数"
            @click="copyText(argsCopyText, 'args')"
          >
            <Check v-if="copiedTarget === 'args'" :size="14" />
            <Copy v-else :size="14" />
          </button>
        </ElTooltip>
        <ElTooltip :content="copiedTarget === 'result' ? '已复制结果' : '复制结果'" placement="bottom">
          <button
            class="icon-button subtle tiny"
            type="button"
            :disabled="!resultCopyText.trim()"
            aria-label="复制工具结果"
            @click="copyText(resultCopyText, 'result')"
          >
            <Check v-if="copiedTarget === 'result'" :size="14" />
            <Copy v-else :size="14" />
          </button>
        </ElTooltip>
        <button class="icon-button subtle" type="button" title="关闭预览" @click="emit('close')">
          <X :size="16" />
        </button>
      </div>
    </header>

    <div class="tool-preview-meta">
      <div v-for="row in detailRows" :key="row.label">
        <span>{{ row.label }}</span>
        <strong :title="row.value">{{ row.value }}</strong>
      </div>
    </div>

    <div v-if="isFailed" class="tool-failure-banner">
      <AlertCircle :size="15" />
      <span>{{ failureMessage }}</span>
    </div>

    <div class="preview-body tool-preview-body">
      <section v-if="kind === 'bash'" class="tool-detail-section terminal-preview">
        <header class="tool-section-header">
          <Terminal :size="15" />
          <strong>终端输出</strong>
          <span v-if="command">{{ command }}</span>
        </header>

        <div class="terminal-window">
          <div class="terminal-title">{{ sessionId || 'shell' }}</div>
          <div class="terminal-output">
            <template v-if="consoleRecords.length > 0">
              <div v-for="(record, index) in consoleRecords" :key="index" class="terminal-record">
                <div class="terminal-command">
                  <span class="prompt">{{ record.ps1 }}</span>
                  <span>{{ record.command }}</span>
                </div>
                <pre v-if="record.output">{{ record.output }}</pre>
              </div>
            </template>
            <span v-else class="muted-text">等待命令输出...</span>
          </div>
        </div>
      </section>

      <section v-else-if="kind === 'browser'" class="tool-detail-section browser-preview">
        <header class="tool-section-header">
          <Globe :size="15" />
          <strong>浏览器页面</strong>
          <span v-if="url">{{ url }}</span>
        </header>

        <div v-if="url" class="address-bar">
          <Globe :size="14" />
          <span>{{ url }}</span>
          <a :href="url" target="_blank" rel="noopener noreferrer" title="打开页面">
            <ExternalLink :size="14" />
          </a>
        </div>
        <div class="browser-shot">
          <img v-if="screenshot" :src="screenshot" alt="浏览器截图">
          <span v-else>等待页面截图...</span>
          <button
            type="button"
            class="vnc-fab"
            title="打开远程桌面"
            @click="emit('openVnc')"
          >
            <Sparkles :size="16" />
          </button>
        </div>
      </section>

      <section v-else-if="kind === 'search'" class="tool-detail-section search-preview">
        <header class="tool-section-header">
          <Search :size="15" />
          <strong>搜索结果</strong>
          <span v-if="query">{{ query }}</span>
        </header>

        <p class="result-summary">
          搜索“{{ query || label }}”的结果 · 共 {{ searchResults.length }} 条
        </p>
        <a
          v-for="(item, index) in searchResults"
          :key="`${item.url}-${index}`"
          class="search-result"
          :href="item.url"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span>{{ item.url }}</span>
          <strong>{{ item.title || item.url }}</strong>
          <p v-if="item.snippet">{{ item.snippet }}</p>
        </a>
        <div v-if="searchResults.length === 0" class="center-state">暂无搜索结果</div>
      </section>

      <section v-else-if="kind === 'file'" class="tool-detail-section terminal-preview">
        <header class="tool-section-header">
          <FileSearch :size="15" />
          <strong>文件内容</strong>
          <span v-if="filepath">{{ filepath }}</span>
        </header>

        <div class="terminal-window light-code">
          <div v-if="filepath" class="terminal-title">{{ filepath }}</div>
          <pre class="terminal-output file-output">{{ fileContent || '等待文件内容...' }}</pre>
        </div>
      </section>

      <section v-else-if="kind === 'mcp' || kind === 'a2a'" class="structured-preview">
        <section class="tool-detail-section">
          <header class="tool-section-header">
            <Braces :size="15" />
            <strong>调用参数</strong>
            <span>{{ tool.name }}</span>
          </header>
          <pre class="structured-code">{{ argsContent || '暂无参数' }}</pre>
        </section>

        <section class="tool-detail-section">
          <header class="tool-section-header">
            <CheckCircle2 :size="15" />
            <strong>执行结果</strong>
            <span>{{ statusLabel }}</span>
          </header>
          <pre class="structured-code result-code">{{ resultContent || '等待执行结果...' }}</pre>
        </section>
      </section>

      <section v-else class="structured-preview">
        <section class="tool-detail-section">
          <header class="tool-section-header">
            <Braces :size="15" />
            <strong>调用参数</strong>
            <span>{{ tool.name || 'tool' }}</span>
          </header>
          <pre class="structured-code">{{ argsContent || '暂无参数' }}</pre>
        </section>

        <section v-if="genericContent" class="tool-detail-section">
          <header class="tool-section-header">
            <CheckCircle2 :size="15" />
            <strong>执行结果</strong>
            <span>{{ statusLabel }}</span>
          </header>
          <pre class="structured-code result-code">{{ genericContent }}</pre>
        </section>
      </section>

      <button class="jump-latest" type="button" @click="emit('jumpToLatest')">
        <Clock3 :size="12" />
        <span>跳转实时</span>
        <Play :size="12" />
      </button>
    </div>
  </aside>
</template>
