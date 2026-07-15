import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/tokens.css'
import './styles/themes.css'
import './style.css'
import './components/chat/chat.css'
import './components/chat/tool-preview.css'
import { initializeTheme } from './lib/theme'

initializeTheme()
const app = createApp(App)

app.use(createPinia())
app.use(router)
app.mount('#app')
