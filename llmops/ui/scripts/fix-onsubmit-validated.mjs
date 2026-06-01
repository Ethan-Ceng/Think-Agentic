/**
 * 将 Arco 风格的 onSubmit({ errors }) 改为 Element Plus formRef.validate()
 */
import fs from 'node:fs'
import path from 'node:path'

const files = [
  'src/views/space/workflows/components/infos/CodeNodeInfo.vue',
  'src/views/space/workflows/components/infos/TemplateTransformNodeInfo.vue',
  'src/views/space/workflows/components/infos/StartNodeInfo.vue',
  'src/views/space/workflows/components/infos/LLMNodeInfo.vue',
  'src/views/space/workflows/components/infos/HttpRequestNodeInfo.vue',
  'src/views/space/workflows/components/infos/EndNodeInfo.vue',
  'src/views/space/workflows/components/infos/DatasetRetrievalNodeInfo.vue',
  'src/views/space/workflows/components/infos/ToolNodeInfo.vue',
]

const blockRe =
  /const onSubmit = async \(\{ errors \}: \{ errors: Record<string, ValidatedError> \| undefined \}\) => \{[\s\S]*?if \(errors\) return\n\n/

const replacement = `const formRef = ref<FormInstance>()
const onSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

`

for (const rel of files) {
  const file = path.join(process.cwd(), rel)
  let s = fs.readFileSync(file, 'utf8')
  if (!blockRe.test(s)) {
    console.warn('skip pattern', rel)
    continue
  }
  s = s.replace(blockRe, replacement)
  if (!s.includes("import type { FormInstance }")) {
    s = s.replace(/import \{ ([^}]+) \} from 'vue'/, "import type { FormInstance } from 'element-plus'\nimport { $1 } from 'vue'")
  }
  if (!s.includes('ref="formRef"')) {
    s = s.replace('<el-form ', '<el-form ref="formRef" ')
  }
  fs.writeFileSync(file, s)
  console.log('fixed', rel)
}
