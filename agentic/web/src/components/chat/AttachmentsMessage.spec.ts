import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AttachmentsMessage from './AttachmentsMessage.vue'

describe('AttachmentsMessage', () => {
  it('opens files with click, Enter and Space and keeps the view-all action separate', async () => {
    const selected = {
      id: 'file-1',
      filename: 'report.md',
      extension: 'md',
      size: 1024,
    }
    const wrapper = mount(AttachmentsMessage, {
      props: {
        role: 'assistant',
        files: [selected],
        showViewAll: true,
      },
    })

    const fileCard = wrapper.get('article.attachment-card')
    expect(fileCard.attributes('tabindex')).toBe('0')
    await fileCard.trigger('click')
    await fileCard.trigger('keydown', { key: 'Enter' })
    await fileCard.trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('fileClick')).toEqual([[selected], [selected], [selected]])

    await wrapper.get('button.view-all-files').trigger('click')
    expect(wrapper.emitted('viewAllFiles')).toHaveLength(1)
  })
})
