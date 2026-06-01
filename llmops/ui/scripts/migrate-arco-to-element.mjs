/**
 * 使用 @vue/compiler-sfc 解析整块 template，避免内部 <template #slot> 导致替换不完整
 */
import fs from 'node:fs'
import path from 'node:path'
import { parse } from 'vue/compiler-sfc'

const srcRoot = path.join(process.cwd(), 'src')

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name)
    if (fs.statSync(p).isDirectory()) walk(p, out)
    else if (name.endsWith('.vue')) out.push(p)
  }
  return out
}

const tagPairsRaw = [
  ['a-collapse-item', 'el-collapse-item'],
  ['a-layout-content', 'el-main'],
  ['a-layout-sider', 'el-aside'],
  ['a-layout-header', 'el-header'],
  ['a-layout-footer', 'el-footer'],
  ['a-layout', 'el-container'],
  ['a-button-group', 'el-button-group'],
  ['a-table-column', 'el-table-column'],
  ['a-carousel-item', 'el-carousel-item'],
  ['a-skeleton-line', 'el-skeleton-item'],
  ['a-tab-pane', 'el-tab-pane'],
  ['a-input-password', 'el-input'],
  ['a-input-search', 'el-input'],
  ['a-checkbox-group', 'el-checkbox-group'],
  ['a-radio-group', 'el-radio-group'],
  ['a-input-number', 'el-input-number'],
  ['a-steps', 'el-steps'],
  ['a-progress', 'el-progress'],
  ['a-trigger', 'el-popover'],
  ['a-alert', 'el-alert'],
  ['a-form-item', 'el-form-item'],
  ['a-dropdown', 'el-dropdown'],
  ['a-doption', 'el-dropdown-item'],
  ['a-textarea', 'el-input'],
  ['a-checkbox', 'el-checkbox'],
  ['a-divider', 'el-divider'],
  ['a-space', 'el-space'],
  ['a-spin', 'div'],
  ['a-skeleton', 'el-skeleton'],
  ['a-empty', 'el-empty'],
  ['a-drawer', 'el-drawer'],
  ['a-modal', 'el-dialog'],
  ['a-tooltip', 'el-tooltip'],
  ['a-image', 'el-image'],
  ['a-link', 'el-link'],
  ['a-carousel', 'el-carousel'],
  ['a-tabs', 'el-tabs'],
  ['a-collapse', 'el-collapse'],
  ['a-card', 'el-card'],
  ['a-row', 'el-row'],
  ['a-col', 'el-col'],
  ['a-select', 'el-select'],
  ['a-option', 'el-option'],
  ['a-switch', 'el-switch'],
  ['a-step', 'el-step'],
  ['a-radio', 'el-radio'],
  ['a-slider', 'el-slider'],
  ['a-tag', 'el-tag'],
  ['a-upload', 'el-upload'],
  ['a-table', 'el-table'],
  ['a-form', 'el-form'],
  ['a-input', 'el-input'],
  ['a-button', 'el-button'],
  ['a-avatar', 'el-avatar'],
]

const tagPairs = [...tagPairsRaw].sort((a, b) => b[0].length - a[0].length)

function migrateTemplate(tpl) {
  let s = tpl

  for (const [from, to] of tagPairs) {
    s = s.split(`<${from}`).join(`<${to}`)
    s = s.split(`<${from}/>`).join(`<${to}/>`)
    s = s.split(`</${from}>`).join(`</${to}>`)
  }

  s = s.replace(/<div([^>]*)\s+:loading="/g, '<div$1 v-loading="')
  s = s.replace(/\sfield="/g, ' prop="')
  s = s.replace(/@submit="/g, '@submit.prevent="')
  s = s.replace(/\slayout="vertical"/g, ' label-position="top"')
  s = s.replace(/html-type="/g, 'native-type="')
  s = s.replace(/\sdestroy-on-hide/g, '')
  s = s.replace(/\s:hide-title(?:="[^"]*")?/g, '')
  s = s.replace(/\s:footer="false"/g, '')
  s = s.replace(/\s:hide-cancel(?:="[^"]*")?/g, '')
  s = s.replace(/\s:mask-closable(?:="[^"]*")?/g, '')
  s = s.replace(/\s:unmount-on-close(?:="[^"]*")?/g, '')
  s = s.replace(/<el-dialog([^>]*)\s+:visible="/g, '<el-dialog$1 v-model="')
  s = s.replace(/<el-drawer([^>]*)\s+:visible="/g, '<el-drawer$1 v-model="')
  s = s.replace(/\sposition="tl"/g, ' placement="top-start"')
  s = s.replace(/\sposition="br"/g, ' placement="bottom-end"')
  s = s.replace(/\sposition="bl"/g, ' placement="bottom-start"')
  s = s.replace(/\sposition="top"/g, ' placement="top"')
  s = s.replace(/:image-url=/g, ':src=')
  s = s.replace(/v-model:model-value=/g, 'v-model=')

  return s
}

function migrateTemplateDeep(tpl) {
  let prev
  let s = tpl
  do {
    prev = s
    s = migrateTemplate(s)
  } while (s !== prev)
  return s
}

function migrateScript(script) {
  let s = script

  s = s.replace(
    /import\s*\{\s*Message\s*,\s*Modal\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    "import { ElMessage } from 'element-plus'",
  )
  s = s.replace(
    /import\s*\{\s*Modal\s*,\s*Message\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    "import { ElMessage } from 'element-plus'",
  )
  s = s.replace(/import\s*\{\s*Message\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    "import { ElMessage } from 'element-plus'",
  )
  s = s.replace(
    /import\s*\{\s*Message\s*,\s*type\s+ValidatedError\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    "import type { FormInstance } from 'element-plus'\nimport { ElMessage } from 'element-plus'",
  )
  s = s.replace(
    /import\s+type\s*\{\s*Form\s*,\s*ValidatedError\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    "import type { FormInstance } from 'element-plus'",
  )
  s = s.replace(
    /import\s+type\s*\{\s*ValidatedError\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    '',
  )
  s = s.replace(
    /import\s*\{\s*type\s+ValidatedError\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    '',
  )
  s = s.replace(
    /import\s*\{\s*type\s+FileItem\s*,\s*Form\s*,\s*type\s+ValidatedError\s*\}\s*from\s*['"]@arco-design\/web-vue['"]/g,
    "import type { FormInstance, UploadUserFile } from 'element-plus'",
  )
  s = s.replace(/\bMessage\.(success|error|warning|info)\b/g, 'ElMessage.$1')

  return s
}

/** 从后往前替换块，避免偏移变化 */
function migrateVueFile(content, filename) {
  const { descriptor, errors } = parse(content, { filename })
  if (errors.length) {
    console.warn(filename, errors.map((e) => e.message).join('; '))
  }

  const blocks = []

  if (descriptor.scriptSetup) {
    blocks.push({
      start: descriptor.scriptSetup.loc.start.offset,
      end: descriptor.scriptSetup.loc.end.offset,
      content: migrateScript(descriptor.scriptSetup.content),
    })
  } else if (descriptor.script) {
    blocks.push({
      start: descriptor.script.loc.start.offset,
      end: descriptor.script.loc.end.offset,
      content: migrateScript(descriptor.script.content),
    })
  }

  if (descriptor.template) {
    blocks.push({
      start: descriptor.template.loc.start.offset,
      end: descriptor.template.loc.end.offset,
      content: migrateTemplateDeep(descriptor.template.content),
    })
  }

  blocks.sort((a, b) => b.start - a.start)

  let result = content
  for (const b of blocks) {
    result = result.slice(0, b.start) + b.content + result.slice(b.end)
  }

  return result
}

for (const file of walk(srcRoot)) {
  const raw = fs.readFileSync(file, 'utf8')
  const rel = path.relative(process.cwd(), file)
  const next = migrateVueFile(raw, rel)
  if (next !== raw) {
    fs.writeFileSync(file, next, 'utf8')
    console.log('migrated', rel)
  }
}

console.log('done')
