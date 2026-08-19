import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import { useSettingsModal } from '@/composables/useSettingsModal'
import SettingsModal from './SettingsModal.vue'

const DialogStub = defineComponent({
  template: '<section><slot name="header" /><slot /><slot name="footer" /></section>',
})

function mountModal() {
  return mount(SettingsModal, {
    global: {
      stubs: {
        ElDialog: DialogStub,
        ElButton: true,
        SettingsAppearancePanel: true,
        SettingsGeneralPanel: true,
        SettingsModelPanel: true,
        StorageSettings: true,
        SettingsApiToolsPanel: true,
        SettingsA2aPanel: true,
        SettingsMcpPanel: true,
      },
    },
  })
}

describe('SettingsModal targeted opening', () => {
  const settingsModal = useSettingsModal()

  afterEach(() => settingsModal.closeSettings())

  it('reopens the same requested panel and enters its mobile detail view', () => {
    settingsModal.openSettings('llm')
    let wrapper = mountModal()

    expect(wrapper.find('.settings-nav-button.active').text()).toContain('模型提供商')
    expect(wrapper.find('.settings-layout').classes()).toContain('mobile-panel-open')

    wrapper.unmount()
    settingsModal.closeSettings()
    settingsModal.openSettings('llm')
    wrapper = mountModal()

    expect(wrapper.find('.settings-nav-button.active').text()).toContain('模型提供商')
    expect(wrapper.find('.settings-layout').classes()).toContain('mobile-panel-open')
  })

  it('keeps the regular settings entry on the category view', () => {
    settingsModal.openSettings()
    const wrapper = mountModal()

    expect(wrapper.find('.settings-nav-button.active').text()).toContain('外观')
    expect(wrapper.find('.settings-layout').classes()).not.toContain('mobile-panel-open')
  })
})
