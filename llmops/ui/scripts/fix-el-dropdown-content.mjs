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

function fixDropdownInTemplate(inner) {
  return inner.replace(
    /<el-dropdown([^>]*)>([\s\S]*?)<template #content>([\s\S]*?)<\/template>\s*<\/el-dropdown>/g,
    '<el-dropdown$1>$2<template #dropdown><el-dropdown-menu>$3</el-dropdown-menu></template></el-dropdown>',
  )
}

function fixFile(content, filename) {
  const { descriptor, errors } = parse(content, { filename })
  if (!descriptor.template || errors.length) return content
  const loc = descriptor.template.loc
  const inner = descriptor.template.content
  if (!inner.includes('<template #content>')) return content
  const next = fixDropdownInTemplate(inner)
  if (next === inner) return content
  return content.slice(0, loc.start.offset) + next + content.slice(loc.end.offset)
}

for (const file of walk(srcRoot)) {
  const raw = fs.readFileSync(file, 'utf8')
  const rel = path.relative(process.cwd(), file)
  const next = fixFile(raw, rel)
  if (next !== raw) {
    fs.writeFileSync(file, next, 'utf8')
    console.log('fixed dropdown', rel)
  }
}
