declare module 'markdown-it' {
  type MarkdownItToken = {
    type: string
    map: [number, number] | null
    markup: string
    info: string
    content: string
  }

  type MarkdownItOptions = Record<string, unknown>

  type MarkdownItRenderer = {
    renderToken(tokens: MarkdownItToken[], index: number, options: MarkdownItOptions): string
    rules: Record<string, MarkdownItRenderRule | undefined>
  }

  type MarkdownItRenderRule = (
    tokens: MarkdownItToken[],
    index: number,
    options: MarkdownItOptions,
    env: unknown,
    self: MarkdownItRenderer,
  ) => string

  export default class MarkdownIt {
    constructor(options?: MarkdownItOptions)
    renderer: MarkdownItRenderer
    utils: {
      escapeHtml(value: string): string
    }
    render(src: string, env?: unknown): string
  }
}
