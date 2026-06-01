<script setup lang="ts">
import { ref } from 'vue'
import LongTermMemoryAbilityItem from './abilities/LongTermMemoryAbilityItem.vue'
import OpeningAbilityItem from './abilities/OpeningAbilityItem.vue'
import SuggestedAfterAnswerAbilityItem from './abilities/SuggestedAfterAnswerAbilityItem.vue'
import ReviewConfigAbilityItem from './abilities/ReviewConfigAbilityItem.vue'
import DatasetsAbilityItem from './abilities/DatasetsAbilityItem.vue'
import ToolsAbilityItem from './abilities/ToolsAbilityItem.vue'
import WorkflowsAbilityItem from './abilities/WorkflowsAbilityItem.vue'
import SpeechToTextAbilityItem from './abilities/SpeechToTextAbilityItem.vue'
import TextToSpeechAbilitiItem from './abilities/TextToSpeechAbilitiItem.vue'

// 1.定义自定义组件所需数据
const props = defineProps({
  app_id: { type: String, default: '', required: true },
  draft_app_config: { type: Object, required: true },
})
const emits = defineEmits(['update:draft_app_config'])
const defaultActivateKeys = [
  'tools',
  'workflows',
  'datasets',
  'long_term_memory',
  'opening',
  'suggested_after_answer',
  'review_config',
  'speech_to_text',
  'text_to_speech',
]
const activeCollapseNames = ref<string[]>([...defaultActivateKeys])
</script>

<template>
  <div class="flex h-full min-h-0 flex-col">
    <!-- 应用能力标题（与左侧「人设」顶栏节奏一致，略留呼吸） -->
    <div class="shrink-0 border-b border-slate-200/75 bg-white/80 px-3 py-2">
      <div class="text-xs font-semibold leading-tight text-slate-900">应用能力</div>
      <div class="mt-0.5 line-clamp-1 text-[11px] leading-snug text-slate-500">
        工具、知识库、记忆与对话体验
      </div>
    </div>
    <!-- 应用能力列表：水平与底部留白，避免与边框贴死 -->
    <div class="min-h-0 flex-1 overflow-y-auto scrollbar-y-sleek px-3">
      <el-collapse v-model="activeCollapseNames" class="min-w-0">
        <!-- 扩展插件组件 -->
        <tools-ability-item
          :tools="props.draft_app_config.tools"
          @update:tools="
            (tools) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                tools: tools,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 工作流组件 -->
        <workflows-ability-item
          :workflows="props.draft_app_config.workflows"
          @update:workflows="
            (workflows) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                workflows,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 知识库组件 -->
        <datasets-ability-item
          :retrieval_config="props.draft_app_config.retrieval_config"
          @update:retrieval_config="
            (retrieval_config) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                retrieval_config,
              })
          "
          :datasets="props.draft_app_config.datasets"
          @update:datasets="
            (datasets) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                datasets,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 长期记忆召回 -->
        <long-term-memory-ability-item
          :long_term_memory="props.draft_app_config.long_term_memory"
          @update:long_term_memory="
            (long_term_memory) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                long_term_memory,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 对话开场白 -->
        <opening-ability-item
          :opening_questions="props.draft_app_config.opening_questions"
          @update:opening_questions="
            (opening_questions) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                opening_questions,
              })
          "
          :opening_statement="props.draft_app_config.opening_statement"
          @update:opening_statement="
            (opening_statement) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                opening_statement,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 回答后生成建议问题 -->
        <suggested-after-answer-ability-item
          :suggested_after_answer="props.draft_app_config.suggested_after_answer"
          @update:suggested_after_answer="
            (suggested_after_answer) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                suggested_after_answer,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 语音输入 -->
        <speech-to-text-ability-item
          :speech_to_text="props.draft_app_config.speech_to_text"
          @update:speech_to_text="
            (speech_to_text) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                speech_to_text,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 语音输出 -->
        <text-to-speech-abiliti-item
          :text_to_speech="props.draft_app_config.text_to_speech"
          @update:text_to_speech="
            (text_to_speech) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                text_to_speech,
              })
          "
          :app_id="props.app_id"
        />
        <!-- 内容审核 -->
        <review-config-ability-item
          :review_config="props.draft_app_config.review_config"
          @update:review_config="
            (review_config) =>
              emits('update:draft_app_config', {
                ...props.draft_app_config,
                review_config,
              })
          "
          :app_id="props.app_id"
        />
      </el-collapse>
    </div>
  </div>
</template>
