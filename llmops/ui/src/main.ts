import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from '@/App.vue'
import router from '@/router'
import { registerAppIcons } from '@/plugins/register-icons'

import 'element-plus/dist/index.css'
import '@/assets/styles/main.css'
import { installScrollbarReveal } from '@/plugins/scrollbar-reveal'

const app = createApp(App)

registerAppIcons(app)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
installScrollbarReveal()
