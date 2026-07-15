<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Activity, ArrowRight, FileText, Loader2, MessageSquare, PanelLeftOpen, Search, Sparkles, Wrench, X } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import SettingsButton from '@/components/SettingsButton.vue'
import UserMenu from '@/components/UserMenu.vue'
import { useSidebar } from '@/composables/useSidebar'
import { searchApi } from '@/lib/api/search'
import type { SearchContentType, SearchResultItem, SearchResults } from '@/lib/api/types'

type HighlightSegment = { text: string; match: boolean }

const route = useRoute()
const router = useRouter()
const sidebar = useSidebar()
const inputRef = ref<HTMLInputElement | null>(null)
const inputValue = ref('')
const loading = ref(false)
const error = ref('')
const results = ref<SearchResults>({
  items: [],
  query: '',
  current_page: 1,
  page_size: 20,
  total_page: 0,
  total_record: 0,
})
let searchTimer = 0
let requestSequence = 0

const routeQuery = computed(() => typeof route.query.q === 'string' ? route.query.q.trim() : '')
const routePage = computed(() => {
  const value = Number(route.query.page || 1)
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 1
})

const typeMeta: Record<SearchContentType, { label: string; icon: typeof MessageSquare }> = {
  session: { label: '任务', icon: Sparkles },
  message: { label: '消息', icon: MessageSquare },
  tool: { label: '工具', icon: Wrench },
  trace: { label: 'Trace', icon: Activity },
  file: { label: '文件', icon: FileText },
}

watch(
  () => [routeQuery.value, routePage.value] as const,
  ([query, page]) => {
    if (inputValue.value !== query) inputValue.value = query
    void loadResults(query, page)
  },
  { immediate: true },
)

onMounted(() => inputRef.value?.focus())
onBeforeUnmount(() => window.clearTimeout(searchTimer))

async function loadResults(query: string, page: number) {
  const sequence = ++requestSequence
  error.value = ''
  if (!query) {
    results.value = { ...results.value, items: [], query: '', current_page: 1, total_page: 0, total_record: 0 }
    loading.value = false
    return
  }

  loading.value = true
  try {
    const data = await searchApi.search({ q: query, current_page: page, page_size: 20 })
    if (sequence === requestSequence) results.value = data
  } catch (reason) {
    if (sequence === requestSequence) {
      error.value = reason instanceof Error ? reason.message : '搜索失败，请稍后重试'
      results.value = { ...results.value, items: [], query, current_page: page, total_page: 0, total_record: 0 }
    }
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function scheduleSearch() {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(submitSearch, 320)
}

function submitSearch() {
  window.clearTimeout(searchTimer)
  const query = inputValue.value.trim()
  if (query === routeQuery.value && routePage.value === 1) {
    void loadResults(query, 1)
    return
  }
  void router.replace({ name: 'search', query: query ? { q: query } : {} })
}

function clearSearch() {
  inputValue.value = ''
  submitSearch()
  inputRef.value?.focus()
}

function changePage(page: number) {
  void router.push({ name: 'search', query: { q: routeQuery.value, page: String(page) } })
}

function openResult(item: SearchResultItem) {
  if (item.session_id) {
    void router.push({
      name: 'session',
      params: { id: item.session_id },
      query: item.event_id ? { focus: item.event_id } : {},
    })
    return
  }
  if (item.content_type === 'file') void router.push('/files')
}

function highlight(value: string): HighlightSegment[] {
  const query = routeQuery.value.toLocaleLowerCase()
  if (!query) return [{ text: value, match: false }]
  const source = value || ''
  const lower = source.toLocaleLowerCase()
  const segments: HighlightSegment[] = []
  let cursor = 0
  while (cursor < source.length) {
    const index = lower.indexOf(query, cursor)
    if (index < 0) {
      segments.push({ text: source.slice(cursor), match: false })
      break
    }
    if (index > cursor) segments.push({ text: source.slice(cursor, index), match: false })
    segments.push({ text: source.slice(index, index + query.length), match: true })
    cursor = index + query.length
  }
  return segments.length ? segments : [{ text: source, match: false }]
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}
</script>

<template>
  <div class="search-page">
    <header class="search-header">
      <div class="search-header-title">
        <button
          v-if="sidebar.mobile.value && !sidebar.open.value"
          class="icon-button"
          type="button"
          aria-label="打开侧边栏"
          @click="sidebar.openSidebar"
        >
          <PanelLeftOpen :size="18" />
        </button>
        <div>
          <h1>全局搜索</h1>
          <p>检索任务、消息、工具调用、Trace 与文件</p>
        </div>
      </div>
      <div class="header-actions"><SettingsButton /><UserMenu /></div>
    </header>

    <main class="search-main">
      <section class="search-hero">
        <form class="global-search-box" role="search" @submit.prevent="submitSearch">
          <Search :size="20" aria-hidden="true" />
          <input
            ref="inputRef"
            v-model="inputValue"
            type="search"
            maxlength="200"
            placeholder="搜索任务、对话、工具或文件"
            aria-label="全局搜索"
            @input="scheduleSearch"
          >
          <button v-if="inputValue" type="button" aria-label="清空搜索" @click="clearSearch">
            <X :size="17" />
          </button>
          <button class="search-submit" type="submit">搜索</button>
        </form>
        <p v-if="routeQuery" class="search-summary" aria-live="polite">
          <template v-if="loading">正在搜索“{{ routeQuery }}”</template>
          <template v-else>找到 {{ results.total_record }} 条与“{{ routeQuery }}”相关的内容</template>
        </p>
      </section>

      <section class="search-results" :aria-busy="loading">
        <div v-if="loading" class="search-loading">
          <Loader2 :size="20" class="spin" />
          <span>正在检索工作区…</span>
        </div>

        <div v-else-if="error" class="search-state error-state" role="alert">
          <h2>搜索暂时不可用</h2>
          <p>{{ error }}</p>
          <button class="button secondary" type="button" @click="loadResults(routeQuery, routePage)">重新搜索</button>
        </div>

        <div v-else-if="!routeQuery" class="search-state">
          <span class="search-state-icon"><Search :size="26" /></span>
          <h2>搜索整个 Agent 工作区</h2>
          <p>输入关键词后，可以找到历史问答、工具执行记录、运行 Trace 和交付文件。</p>
        </div>

        <div v-else-if="results.items.length === 0" class="search-state">
          <span class="search-state-icon"><Search :size="26" /></span>
          <h2>没有找到匹配内容</h2>
          <p>尝试缩短关键词，或使用任务标题、工具名和文件名搜索。</p>
        </div>

        <div v-else class="search-result-list">
          <button
            v-for="item in results.items"
            :key="item.id"
            class="search-result-card"
            type="button"
            @click="openResult(item)"
          >
            <span class="result-type-icon" :class="`type-${item.content_type}`">
              <component :is="typeMeta[item.content_type].icon" :size="17" />
            </span>
            <span class="result-content">
              <span class="result-meta">
                <b>{{ typeMeta[item.content_type].label }}</b>
                <span v-if="formatDate(item.created_at)">{{ formatDate(item.created_at) }}</span>
              </span>
              <strong>
                <template v-for="(segment, index) in highlight(item.title)" :key="index">
                  <mark v-if="segment.match">{{ segment.text }}</mark><template v-else>{{ segment.text }}</template>
                </template>
              </strong>
              <p>
                <template v-for="(segment, index) in highlight(item.snippet)" :key="index">
                  <mark v-if="segment.match">{{ segment.text }}</mark><template v-else>{{ segment.text }}</template>
                </template>
              </p>
            </span>
            <ArrowRight :size="17" class="result-arrow" />
          </button>
        </div>

        <ElPagination
          v-if="!loading && results.total_record > results.page_size"
          :current-page="results.current_page"
          :page-size="results.page_size"
          :total="results.total_record"
          layout="prev, pager, next"
          class="search-pagination"
          @current-change="changePage"
        />
      </section>
    </main>
  </div>
</template>

<style scoped>
.search-page { display: flex; flex-direction: column; width: 100%; height: 100%; min-width: 0; background: var(--surface-canvas); }
.search-header { display: flex; align-items: center; justify-content: space-between; min-height: 64px; padding: 0 22px; border-bottom: 1px solid var(--border-light); background: var(--surface-primary); }
.search-header-title, .header-actions { display: flex; align-items: center; gap: 10px; }
.search-header h1 { color: var(--text-primary); font-size: 17px; }.search-header p { color: var(--text-tertiary); font-size: 12px; }
.search-main { flex: 1; min-height: 0; overflow-y: auto; padding: 40px 24px 64px; }
.search-hero, .search-results { width: min(820px, 100%); margin: 0 auto; }
.global-search-box { display: flex; align-items: center; gap: 11px; width: 100%; min-height: 58px; padding: 7px 8px 7px 17px; border: 1px solid var(--border-medium); border-radius: var(--radius-lg); background: var(--surface-primary); color: var(--text-tertiary); box-shadow: var(--shadow-md); }
.global-search-box:focus-within { border-color: var(--accent-primary); box-shadow: var(--shadow-md), var(--focus-ring); }
.global-search-box input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); font-size: 16px; }
.global-search-box > button:not(.search-submit) { display: inline-flex; padding: 7px; border-radius: var(--radius-sm); background: transparent; color: var(--text-tertiary); cursor: pointer; }
.search-submit { min-height: 42px; padding: 0 18px; border-radius: var(--radius-md); background: var(--accent-primary); color: var(--accent-contrast); cursor: pointer; font-size: var(--text-sm); font-weight: 700; }
.search-summary { min-height: 20px; margin: 12px 4px 20px; color: var(--text-tertiary); font-size: var(--text-sm); }
.search-loading { display: flex; align-items: center; justify-content: center; gap: 9px; min-height: 240px; color: var(--text-secondary); }
.search-state { display: flex; align-items: center; flex-direction: column; justify-content: center; min-height: 330px; padding: 32px; text-align: center; }
.search-state-icon { display: inline-flex; align-items: center; justify-content: center; width: 56px; height: 56px; margin-bottom: 16px; border-radius: var(--radius-lg); background: var(--accent-soft); color: var(--accent-primary); }
.search-state h2 { color: var(--text-primary); font-size: 18px; }.search-state p { max-width: 480px; margin-top: 6px; color: var(--text-tertiary); font-size: var(--text-sm); line-height: 1.6; }
.error-state .button { margin-top: 16px; padding: 0 14px; }
.search-result-list { display: flex; flex-direction: column; gap: 8px; }
.search-result-card { display: grid; grid-template-columns: 38px minmax(0, 1fr) 24px; align-items: start; gap: 12px; width: 100%; padding: 15px; border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--surface-primary); color: var(--text-secondary); cursor: pointer; text-align: left; transition: border-color var(--motion-fast) ease, box-shadow var(--motion-fast) ease, transform var(--motion-fast) ease; }
.search-result-card:hover { border-color: var(--border-medium); box-shadow: var(--shadow-sm); transform: translateY(-1px); }
.result-type-icon { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: var(--radius-md); background: var(--surface-secondary); color: var(--text-secondary); }
.result-type-icon.type-message { background: var(--accent-soft); color: var(--accent-primary); }.result-type-icon.type-tool { background: var(--status-warning-soft); color: var(--status-warning); }.result-type-icon.type-trace { background: var(--status-info-soft); color: var(--status-info); }.result-type-icon.type-file { background: var(--status-success-soft); color: var(--status-success); }
.result-content { display: flex; flex-direction: column; gap: 4px; min-width: 0; }.result-meta { display: flex; align-items: center; gap: 8px; color: var(--text-tertiary); font-size: 11px; }.result-meta b { color: var(--text-secondary); font-weight: 700; }
.result-content > strong { overflow: hidden; color: var(--text-primary); font-size: var(--text-base); font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }.result-content p { display: -webkit-box; overflow: hidden; color: var(--text-secondary); font-size: var(--text-sm); line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
mark { padding: 1px 2px; border-radius: 3px; background: var(--status-warning-soft); color: var(--text-primary); }.result-arrow { align-self: center; color: var(--text-tertiary); }
.search-pagination { justify-content: center; margin-top: 24px; }
@media (max-width: 640px) { .search-header { padding: 0 12px; }.search-header p, .header-actions .user-label { display: none; }.search-main { padding: 24px 14px 48px; }.global-search-box { min-height: 52px; padding-left: 13px; }.search-submit { min-height: 38px; padding: 0 13px; }.search-result-card { grid-template-columns: 34px minmax(0, 1fr); padding: 12px; }.result-type-icon { width: 34px; height: 34px; }.result-arrow { display: none; } }
</style>
