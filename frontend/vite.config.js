import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import llmProxy from './vite-llm-proxy.js'

// Tailwind reads tailwind.config.js once when the dev server starts, so a new colour/token would make
// every page show a CSS error until a manual restart. Restart the dev server automatically instead.
function restartOnTailwindConfig() {
  return {
    name: 'restart-on-tailwind-config',
    configureServer(server) {
      const file = path.resolve('tailwind.config.js')
      server.watcher.add(file)
      server.watcher.on('change', (changed) => {
        if (path.resolve(changed) === file) server.restart()
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  // llmProxy lets the app use the model configured in ../.env without exposing the key to the browser.
  plugins: [react(), llmProxy(), restartOnTailwindConfig()],
  server: {
    port: 3000,
    host: true,
  }
})
