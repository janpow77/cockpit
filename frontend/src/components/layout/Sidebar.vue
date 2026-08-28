<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  LayoutDashboard, Server, AppWindow, Github, Database, KeyRound, History, Settings, Plane,
  Activity, Rocket, Radar, MessageSquare, Plug, KanbanSquare } from 'lucide-vue-next'

const props = defineProps<{ open?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const schublade = ref<HTMLElement | null>(null)
const istMobil = ref(false)
let media: MediaQueryList | undefined

function mediaAktualisieren(event?: MediaQueryListEvent) { istMobil.value = event?.matches ?? media?.matches ?? false }
function tastatur(event: KeyboardEvent) { if (event.key === 'Escape' && props.open) emit('close') }

watch(() => props.open, async (offen) => {
  if (!offen || !istMobil.value) return
  await nextTick()
  schublade.value?.focus()
})

onMounted(() => {
  media = window.matchMedia('(max-width: 767px)')
  mediaAktualisieren()
  media.addEventListener('change', mediaAktualisieren)
  document.addEventListener('keydown', tastatur)
})
onBeforeUnmount(() => {
  media?.removeEventListener('change', mediaAktualisieren)
  document.removeEventListener('keydown', tastatur)
})

const items = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { to: '/hosts', label: 'Hosts', icon: Server },
  { to: '/apps', label: 'Apps', icon: AppWindow },
  { to: '/traffic', label: 'Traffic', icon: Activity },
  { to: '/deployments', label: 'Deployments', icon: Rocket },
  { to: '/github', label: 'GitHub', icon: Github },
  { to: '/backups', label: 'Backups', icon: Database },
  { to: '/secrets', label: 'Secrets', icon: KeyRound },
  { to: '/audit', label: 'Audit', icon: History },
  { to: '/wall', label: 'Cockpit', icon: Radar },
  { to: '/chat', label: 'LLM-Konsole', icon: MessageSquare },
  { to: '/kanban', label: 'Aufträge', icon: KanbanSquare },
  { to: '/mcp', label: 'MCP-Server', icon: Plug },
  { to: '/settings', label: 'Einstellungen', icon: Settings },
]
</script>

<template>
  <Transition name="schublade-blende">
    <button v-if="open && istMobil" type="button" class="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-[1px] md:hidden" aria-label="Navigation schließen" @click="$emit('close')" />
  </Transition>
  <aside
    id="mobile-sidebar"
    ref="schublade"
    tabindex="-1"
    :inert="istMobil && !open"
    :aria-hidden="istMobil && !open ? 'true' : undefined"
    class="fixed inset-y-0 left-0 z-50 flex w-[264px] shrink-0 flex-col border-r border-slate-200/70 shadow-2xl transition-transform duration-200 motion-reduce:transition-none dark:border-slate-800/70 md:static md:z-auto md:translate-x-0 md:shadow-none"
    :class="open ? 'translate-x-0' : '-translate-x-full pointer-events-none md:pointer-events-auto'"
    style="background: var(--sidebar-bg)"
  >
    <div class="px-5 pt-5 pb-4 border-b border-slate-200/70 dark:border-slate-800/70">
      <RouterLink to="/" class="flex items-center gap-2.5" @click="$emit('close')">
        <div class="grid place-items-center h-9 w-9 rounded-lg bg-sky-600 text-white shadow-sm">
          <Plane :size="18" />
        </div>
        <div>
          <p class="font-semibold tracking-tight text-slate-900 dark:text-slate-100 leading-none">Cockpit</p>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Multi-Host-Verwaltung</p>
        </div>
      </RouterLink>
    </div>

    <nav class="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
      <RouterLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        :exact-active-class="item.exact ? 'bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300' : ''"
        active-class="bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300"
        class="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors"
        @click="$emit('close')"
      >
        <component :is="item.icon" :size="16" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="px-5 py-3 border-t border-slate-200/70 dark:border-slate-800/70 text-xs text-slate-500 dark:text-slate-500">
      <p>v0.3.24 · Cockpit, LLM-Konsole, MCP</p>
    </div>
  </aside>
</template>

<style scoped>
.schublade-blende-enter-active, .schublade-blende-leave-active { transition: opacity .2s ease; }
.schublade-blende-enter-from, .schublade-blende-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .schublade-blende-enter-active, .schublade-blende-leave-active { transition-duration: .001ms; }
}
</style>
