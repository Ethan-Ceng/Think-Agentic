declare module '@novnc/novnc' {
  export default class RFB extends EventTarget {
    viewOnly: boolean
    scaleViewport: boolean
    background: string

    constructor(
      target: HTMLElement,
      url: string,
      options?: {
        credentials?: {
          password?: string
          username?: string
          target?: string
        }
      },
    )

    disconnect(): void
  }
}
