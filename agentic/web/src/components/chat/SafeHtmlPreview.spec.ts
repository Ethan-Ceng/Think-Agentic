import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SafeHtmlPreview from './SafeHtmlPreview.vue'

describe('SafeHtmlPreview', () => {
  it('wraps untrusted HTML in a no-permission sandbox with a restrictive CSP', () => {
    const content = [
      '<script>window.parent.document.body.innerHTML = "owned"</script>',
      '<img src="https://tracker.example/pixel.png">',
      '<form action="https://attacker.example"><button>send</button></form>',
    ].join('')
    const wrapper = mount(SafeHtmlPreview, {
      props: {
        title: 'Unsafe demo',
        content,
      },
    })

    const iframe = wrapper.get('iframe')
    expect(iframe.attributes('sandbox')).toBe('')
    expect(iframe.attributes('referrerpolicy')).toBe('no-referrer')
    expect(iframe.attributes('title')).toBe('Unsafe demo 安全预览')

    const srcdoc = iframe.attributes('srcdoc')
    expect(srcdoc).toBeDefined()
    if (!srcdoc) throw new Error('Expected iframe srcdoc')
    expect(srcdoc.indexOf('Content-Security-Policy')).toBeLessThan(srcdoc.indexOf('<script>'))
    expect(srcdoc).toContain("default-src 'none'")
    expect(srcdoc).toContain("script-src 'none'")
    expect(srcdoc).toContain("connect-src 'none'")
    expect(srcdoc).toContain("worker-src 'none'")
    expect(srcdoc).toContain("navigate-to 'none'")
    expect(srcdoc).toContain("form-action 'none'")
    expect(srcdoc).toContain("base-uri 'none'")
    expect(srcdoc).toContain("object-src 'none'")
    expect(srcdoc).toContain("frame-src 'none'")
    expect(srcdoc).toContain('<script>window.parent.document.body.innerHTML = "owned"</script>')
    expect(srcdoc).toContain('<img>')
    expect(srcdoc).toContain('<form><button>send</button></form>')
    expect(srcdoc).not.toContain('https://attacker.example')
    expect(srcdoc).not.toContain('https://tracker.example')
  })

  it('refuses to render content above the configured byte limit', () => {
    const wrapper = mount(SafeHtmlPreview, {
      props: {
        title: 'Large demo',
        content: '中文内容',
        maxContentBytes: 5,
      },
    })

    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('内容过大')
    expect(wrapper.text()).toContain('查看源码或下载')
  })

  it('removes document navigation while preserving visible preview content', () => {
    const wrapper = mount(SafeHtmlPreview, {
      props: {
        title: 'Navigation demo',
        content: [
          '<meta http-equiv="refresh" content="0;url=https://attacker.example/refresh">',
          '<a href="https://attacker.example/link" ping="https://attacker.example/ping">Open docs</a>',
          '<form action="https://attacker.example/form">',
          '<button formaction="https://attacker.example/button">Submit</button>',
          '</form>',
          '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">',
          '<img src="https://attacker.example/image.png" srcset="https://attacker.example/image-2x.png 2x">',
          '<svg><a href="https://attacker.example/svg"><text>SVG link</text></a></svg>',
        ].join(''),
      },
    })

    const srcdoc = wrapper.get('iframe').attributes('srcdoc')
    expect(srcdoc).toContain('Open docs')
    expect(srcdoc).toContain('Submit')
    expect(srcdoc).toContain('SVG link')
    expect(srcdoc).toContain('src="data:image/gif;base64,')
    expect(srcdoc).not.toContain('attacker.example')
    expect(srcdoc).not.toContain('http-equiv="refresh"')
    expect(srcdoc).not.toContain('formaction=')
    expect(srcdoc).not.toContain(' ping=')
  })
})
