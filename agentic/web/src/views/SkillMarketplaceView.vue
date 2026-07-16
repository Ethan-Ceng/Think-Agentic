<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Search, Store } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import MarketplaceSkillCard from '@/components/skills/MarketplaceSkillCard.vue'
import MarketplaceSkillDetail from '@/components/skills/MarketplaceSkillDetail.vue'
import { useSkillsStore } from '@/stores/skills'

const router = useRouter()
const store = useSkillsStore()
const search = ref('')
const selectedId = ref('')
const busy = ref(false)

const filtered = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  if (!query) return store.marketplace
  return store.marketplace.filter((skill) =>
    `${skill.display_name} ${skill.name} ${skill.description}`.toLocaleLowerCase().includes(query),
  )
})
const selected = computed(() =>
  store.marketplace.find((skill) => skill.id === selectedId.value) ?? filtered.value[0] ?? null,
)

watch(filtered, (items) => {
  if (!items.some((skill) => skill.id === selectedId.value)) selectedId.value = items[0]?.id ?? ''
})

async function mutate(action: 'install' | 'update' | 'uninstall' | 'fork'): Promise<void> {
  if (!selected.value) return
  busy.value = true
  try {
    if (action === 'install') await store.installMarketplace(selected.value.id)
    if (action === 'update') await store.updateMarketplace(selected.value.id)
    if (action === 'uninstall') await store.uninstallMarketplace(selected.value.id)
    if (action === 'fork') {
      const draft = await store.forkMarketplace(selected.value.id)
      await router.push({ name: 'skills', query: { draft: draft.draft_id } })
    }
  } catch {
    // The store keeps the prior state and exposes the backend message.
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    const items = await store.loadMarketplace()
    selectedId.value = items[0]?.id ?? ''
  } catch {
    // Rendered from marketplaceError.
  }
})
</script>

<template>
  <div class="marketplace-view">
    <header>
      <RouterLink to="/skills"><ArrowLeft :size="16" />我的 Skills</RouterLink>
      <div><h1><Store :size="22" />Skill 市场</h1><p>浏览部署方维护的不可变 Skill，并按用户固定安装版本。</p></div>
    </header>
    <label class="search-box">
      <Search :size="16" />
      <input v-model="search" data-testid="marketplace-search" type="search" placeholder="搜索名称或说明">
    </label>
    <p v-if="store.marketplaceError" class="marketplace-error">{{ store.marketplaceError }}</p>
    <div v-if="store.loading && !store.marketplace.length" class="page-state">正在加载 Skill 市场…</div>
    <div v-else-if="!filtered.length" class="page-state">没有匹配的 Marketplace Skill。</div>
    <div v-else class="marketplace-layout">
      <section class="marketplace-grid" aria-label="Marketplace Skills">
        <MarketplaceSkillCard
          v-for="skill in filtered"
          :key="skill.id"
          :skill="skill"
          :selected="selected?.id === skill.id"
          @select="selectedId = skill.id"
        />
      </section>
      <MarketplaceSkillDetail
        v-if="selected"
        :skill="selected"
        :busy="busy"
        @install="mutate('install')"
        @update="mutate('update')"
        @uninstall="mutate('uninstall')"
        @fork="mutate('fork')"
      />
    </div>
  </div>
</template>

<style scoped>
.marketplace-view { display: flex; flex-direction: column; gap: 18px; height: 100%; padding: 24px 28px; overflow: auto; }
header { display: flex; align-items: center; gap: 16px; } header > div { flex: 1; }
header a { display: inline-flex; align-items: center; gap: 5px; min-height: 36px; padding: 0 10px; border: 1px solid var(--border-light); border-radius: 7px; color: var(--text-secondary); text-decoration: none; }
h1, p { margin: 0; } h1 { display: flex; align-items: center; gap: 8px; color: var(--text-primary); font-size: 24px; } header p { margin-top: 4px; color: var(--text-secondary); font-size: 13px; }
.search-box { display: flex; align-items: center; gap: 7px; max-width: 520px; min-height: 40px; padding: 0 11px; border: 1px solid var(--border-light); border-radius: 8px; color: var(--text-tertiary); background: var(--surface-primary); }
.search-box input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); }
.marketplace-error { padding: 10px 12px; border: 1px solid color-mix(in srgb, var(--status-error) 30%, transparent); border-radius: 7px; color: var(--status-error); font-size: 13px; }
.marketplace-layout { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(320px, .8fr); align-items: start; gap: 16px; }
.marketplace-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
@media (max-width: 860px) { .marketplace-view { padding: 18px; } .marketplace-layout { grid-template-columns: 1fr; } header { align-items: flex-start; } }
</style>
