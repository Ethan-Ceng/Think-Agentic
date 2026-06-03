<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed, watch } from 'vue'
import { useGetDraftAppConfig } from '@/hooks/use-app'
import AgentAppAbility from './components/AgentAppAbility.vue'
import DraftAppConfigSplit from './components/DraftAppConfigSplit.vue'
import ModelConfig from './components/ModelConfig.vue'
import PlannerAgentAbility from './components/PlannerAgentAbility.vue'
import PresetPromptTextarea from './components/PresetPromptTextarea.vue'
import PreviewDebugChat from './components/PreviewDebugChat.vue'
import PreviewDebugHeader from './components/PreviewDebugHeader.vue'

const route = useRoute()
const props = defineProps({
  app: {
    type: Object,
    default: () => ({}),
    required: true,
  },
})
const { draftAppConfigForm, loadDraftAppConfig } = useGetDraftAppConfig()
const isPlannerApp = computed(() => props.app?.agent_type === 'planner')

watch(
  () => route.params.app_id,
  async (app_id) => {
    if (!app_id) return
    await loadDraftAppConfig(String(app_id))
  },
  { immediate: true },
)
</script>

<template>
  <div
    class="detail-orchestrate flex h-full min-h-0 w-full flex-col bg-slate-100/85 bg-[radial-gradient(ellipse_120%_80%_at_50%_-20%,rgb(224_231_255/0.42),transparent)]"
  >
    <el-container
      direction="horizontal"
      class="orchestrate-shell !m-0 !h-full !min-h-0 !min-w-0 !flex-1 !overflow-hidden !p-0"
    >
      <!-- 左侧：编排 -->
      <el-container
        direction="vertical"
        class="!m-0 !flex !min-h-0 !min-w-0 !flex-1 !flex-col !overflow-hidden border-slate-200/70 xl:!border-r"
      >
        <el-header
          class="!flex !h-auto !min-h-[4.25rem] !items-center !gap-4 !border-b !border-slate-200/60 !bg-white/95 !px-4 !py-3 !backdrop-blur-sm"
        >
          <div class="flex min-w-0 flex-1 items-center gap-3">
            <div
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-md shadow-indigo-500/25"
              aria-hidden="true"
            >
              <icon-apps class="text-lg" />
            </div>
            <div class="min-w-0">
              <div class="text-sm font-semibold tracking-tight text-slate-900">应用编排</div>
              <div class="truncate text-xs text-slate-500">人设、能力与模型</div>
            </div>
          </div>
          <div class="flex shrink-0 items-center border-l border-slate-200/70 pl-4">
            <model-config
              :dialog_round="draftAppConfigForm.dialog_round"
              v-model:model_config="draftAppConfigForm.model_config"
              :app_id="String(route.params?.app_id)"
            />
          </div>
        </el-header>
        <el-main class="editor-main !m-0 !min-h-0 !flex-1 !overflow-hidden !bg-transparent !p-0">
          <draft-app-config-split>
            <template #preset>
              <preset-prompt-textarea
                class="h-full min-h-0"
                v-model:preset_prompt="draftAppConfigForm.preset_prompt"
                :app_id="String(route.params?.app_id)"
              />
            </template>
            <template #abilities>
              <agent-app-ability
                v-if="!isPlannerApp"
                class="h-full min-h-0"
                v-model:draft_app_config="draftAppConfigForm"
                :app_id="String(route.params?.app_id)"
              />
              <planner-agent-ability
                v-else
                class="h-full min-h-0"
                :app_id="String(route.params?.app_id)"
              />
            </template>
          </draft-app-config-split>
        </el-main>
      </el-container>

      <!-- 右侧：预览与调试 -->
      <el-aside
        width="420px"
        class="preview-aside !m-0 flex !w-full !min-w-0 !max-w-none flex-col !overflow-hidden border-t border-slate-200/60 bg-gradient-to-b from-white via-slate-50/35 to-slate-50/90 !p-0 shadow-none xl:!w-[min(420px,40vw)] xl:!max-w-[480px] xl:!shrink-0 xl:!border-l xl:!border-t-0 xl:shadow-[inset_10px_0_28px_-18px_rgba(15,23,42,0.07)]"
      >
        <preview-debug-header
          :app_id="String(route.params?.app_id)"
          :long_term_memory="draftAppConfigForm.long_term_memory"
        />
        <preview-debug-chat
          class="min-h-0 flex-1"
          :suggested_after_answer="draftAppConfigForm.suggested_after_answer"
          :opening_questions="draftAppConfigForm.opening_questions"
          :opening_statement="draftAppConfigForm.opening_statement"
          :text_to_speech="draftAppConfigForm.text_to_speech"
          :app="props.app"
          :app_id="props.app?.id"
        />
      </el-aside>
    </el-container>
  </div>
</template>

<style scoped>
.detail-orchestrate :deep(.orchestrate-shell.el-container) {
  flex-direction: column !important;
}

.detail-orchestrate :deep(.preview-aside.el-aside) {
  width: 100% !important;
}

@media (min-width: 1280px) {
  .detail-orchestrate :deep(.orchestrate-shell.el-container) {
    flex-direction: row !important;
  }

  .detail-orchestrate :deep(.preview-aside.el-aside) {
    width: min(420px, 40vw) !important;
    max-width: 480px;
  }
}

.detail-orchestrate :deep(.editor-main.el-main) {
  --el-main-padding: 0;
}
</style>
