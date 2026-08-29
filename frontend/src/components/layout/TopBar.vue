<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useThemeStore } from '../../stores/theme'
import { useAuthStore } from '../../stores/auth'
import { useRouter } from 'vue-router'
import { Sun, Moon, LogOut, Menu } from 'lucide-vue-next'
import { getHealth } from '../../api/dashboard'
import { getSettings } from '../../api/settings'
import Badge from '../shared/Badge.vue'
import type { HealthInfo, Settings } from '../../api/types'

defineProps<{ menuOpen?: boolean }>()
defineEmits<{ toggleMenu: [] }>()

const theme = useThemeStore()
const auth = useAuthStore()
const router = useRouter()

const health = ref<HealthInfo | null>(null)
const settings = ref<Settings | null>(null)

onMounted(async () => {
  try { health.value = await getHealth() } catch { /* ignore */ }
  try { settings.value = await getSettings() } catch { /* ignore */ }
})

async function doLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <header
    class="sticky top-0 z-30 flex items-center justify-between gap-4 px-6 py-3 border-b border-slate-200/70 dark:border-slate-800/70 backdrop-blur-md"
    style="background: var(--sidebar-bg)"
  >
    <div class="flex items-center gap-3">
      <button type="button" class="md:hidden grid place-items-center h-9 w-9 rounded-lg bg-sky-600 text-white" aria-label="Navigation öffnen" aria-controls="mobile-sidebar" :aria-expanded="menuOpen" @click="$emit('toggleMenu')">
        <Menu :size="18" />
      </button>
      <div>
        <h1 class="text-sm font-semibold text-slate-900 dark:text-slate-100 capitalize">{{ String($route.name || 'Cockpit') }}</h1>
        <p v-if="health" class="text-xs text-slate-500 dark:text-slate-400 leading-tight">
          Cockpit v{{ health.version }} · uptime {{ Math.floor((health.uptime_s || 0) / 60) }} min
        </p>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <Badge v-if="settings && settings.admin_password_is_default" variant="amber" dot>Default-PW aktiv</Badge>
      <Badge v-if="health" :variant="health.status === 'ok' ? 'green' : health.status === 'degraded' ? 'amber' : 'red'" dot>
        {{ health.status === 'ok' ? 'Online' : health.status === 'degraded' ? 'Degraded' : 'Offline' }}
      </Badge>

      <button
        class="grid place-items-center h-9 w-9 rounded-md text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        :title="theme.theme === 'dark' ? 'Light Mode' : 'Dark Mode'"
        @click="theme.toggle"
      >
        <Sun v-if="theme.theme === 'dark'" :size="16" />
        <Moon v-else :size="16" />
      </button>

      <button
        class="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        title="Abmelden"
        @click="doLogout"
      >
        <LogOut :size="14" />
        <span class="hidden sm:inline">Abmelden</span>
      </button>
    </div>
  </header>
</template>
