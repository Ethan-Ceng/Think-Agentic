import { mergeConfig } from 'vite'
import { defineConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'happy-dom',
      setupFiles: ['./src/test/setup.ts'],
      clearMocks: true,
      server: {
        deps: {
          inline: ['element-plus'],
        },
      },
    },
  }),
)
