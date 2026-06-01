import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

type ToastKind = 'success' | 'error' | 'info'

function push(kind: ToastKind, message: string): void {
  ElMessage({
    type: kind,
    message,
    duration: 3500,
    showClose: true,
    grouping: true,
  })
}

export function useToast() {
  return {
    success: (message: string) => push('success', message),
    error: (message: string) => push('error', message),
    info: (message: string) => push('info', message),
  }
}
