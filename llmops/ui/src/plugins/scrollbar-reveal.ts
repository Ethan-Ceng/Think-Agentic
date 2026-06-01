const SCROLL_CLASS = 'scrollbar-y-sleek--scrolling'

const bound = new WeakSet<HTMLElement>()
const scrollTimers = new WeakMap<HTMLElement, ReturnType<typeof setTimeout>>()

function flash(el: HTMLElement) {
  el.classList.add(SCROLL_CLASS)
  const prev = scrollTimers.get(el)
  if (prev !== undefined) clearTimeout(prev)
  scrollTimers.set(
    el,
    setTimeout(() => {
      el.classList.remove(SCROLL_CLASS)
      scrollTimers.delete(el)
    }, 900),
  )
}

function bindScrollTarget(el: HTMLElement) {
  if (bound.has(el)) return
  bound.add(el)
  el.addEventListener('scroll', () => flash(el), { passive: true })
}

function scan(root: ParentNode) {
  root.querySelectorAll('.scrollbar-y-sleek').forEach((node) => bindScrollTarget(node as HTMLElement))
  root.querySelectorAll('.preset-prompt-textarea textarea').forEach((node) =>
    bindScrollTarget(node as HTMLElement),
  )
}

/** 滚动时短暂加上 SCROLL_CLASS，配合 main.css 显示滚动条 */
export function installScrollbarReveal() {
  const appRoot = document.getElementById('app')
  if (!appRoot) return

  scan(document)

  let t: ReturnType<typeof setTimeout> | undefined
  const schedule = () => {
    if (t !== undefined) return
    t = setTimeout(() => {
      t = undefined
      scan(appRoot)
    }, 50)
  }

  const mo = new MutationObserver(schedule)
  mo.observe(appRoot, { childList: true, subtree: true })

  const onWinScroll = () => {
    flash(document.documentElement)
    flash(document.body)
  }
  window.addEventListener('scroll', onWinScroll, { passive: true })
}
