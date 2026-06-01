<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import RFB from '@novnc/novnc'
import type { VNCStatus } from '@/types/vnc'

const props = withDefaults(defineProps<{
  url: string
  viewOnly?: boolean
}>(), {
  viewOnly: false,
})

const emit = defineEmits<{
  statusChange: [status: VNCStatus, detail?: string]
}>()

const displayRef = ref<HTMLDivElement | null>(null)
let rfb: RFB | null = null

function disconnect() {
  try {
    rfb?.disconnect()
  } catch {
    // noop
  }
  rfb = null
}

function connect() {
  if (!displayRef.value) return
  disconnect()

  emit('statusChange', 'connecting')
  try {
    rfb = new RFB(displayRef.value, props.url, {
      credentials: { password: '', username: '', target: '' },
    })

    rfb.viewOnly = props.viewOnly
    rfb.scaleViewport = true
    rfb.background = '#000'

    rfb.addEventListener('connect', () => emit('statusChange', 'connected'))
    rfb.addEventListener('disconnect', (event: Event) => {
      const detail = (event as CustomEvent<{ clean?: boolean }>).detail
      if (detail?.clean) {
        emit('statusChange', 'disconnected', '连接已断开')
      } else {
        emit('statusChange', 'error', '沙箱环境可能已关闭或连接异常断开')
      }
    })
    rfb.addEventListener('securityfailure', () => {
      emit('statusChange', 'error', '认证失败，无法连接到沙箱')
    })
  } catch {
    emit('statusChange', 'error', '无法建立连接，沙箱环境可能未启动')
  }
}

watch(
  () => props.url,
  () => connect(),
  { flush: 'post' },
)

onMounted(() => {
  void nextTick(connect)
})

onBeforeUnmount(disconnect)
</script>

<template>
  <div ref="displayRef" class="vnc-display" />
</template>
