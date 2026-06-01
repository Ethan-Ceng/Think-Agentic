import { ElMessageBox } from 'element-plus'

/** 与 Arco `Modal.warning` + `onOk` 等价的确认框 */
export function confirmWarning(
  title: string,
  content: string,
  onOk: () => void | Promise<void>,
): void {
  ElMessageBox.confirm(content, title, {
    type: 'warning',
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    draggable: true,
  })
    .then(() => onOk())
    .catch(() => {})
}
