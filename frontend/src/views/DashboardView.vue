<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Server, AppWindow, Database, KeyRound, AlertTriangle, Activity, Github } from 'lucide-vue-next'
import Card from '../components/shared/Card.vue'
import Badge from '../components/shared/Badge.vue'
import Spinner from '../components/shared/Spinner.vue'
import EmptyState from '../components/shared/EmptyState.vue'
import { getDashboard } from '../api/dashboard'
import { listHosts } from '../api/hosts'
import { listApps } from '../api/apps'
import { usePollStore } from '../stores/poll'
import { extractError } from '../api/client'
import { formatNumber, relativeTime, statusVariant } from '../utils/format'
import type { DashboardStats, Host, App } from '../api/types'

const stats = ref<DashboardStats | null>(null)
const hosts = ref<Host[]>([])
const apps = ref<App[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const poll = usePollStore()

async function load() {
  try {
    error.value = null
    const [s, h, a] = await Promise.all([getDashboard(), listHosts(), listApps()])
    stats.value = s
    hosts.value = h
    apps.value = a
  } catch (err) {
    error.value = extractError(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  poll.start('dashboard', load, 30_000)
})

onBeforeUnmount(() => {
  poll.stop('dashboard')
})

const heroStats = computed(() => {
  if (!stats.value) return []
  return [
    { label: 'Apps gesamt', value: formatNumber(stats.value.apps_total), icon: AppWindow, accent: 'sky',
      sub: `${stats.value.apps_healthy} healthy / ${stats.value.apps_down} down` },
    { label: 'Hosts online', value: `${stats.value.hosts_online} / ${stats.value.hosts_total}`, icon: Server, accent: 'green',
      sub: 'Tailscale-Reachability' },
    { label: 'Backups', value: formatNumber(stats.value.backups_total), icon: Database, accent: 'amber',
      sub: stats.value.last_backup_at ? `letzter ${relativeTime(stats.value.last_backup_at)}` : 'noch nie' },
    { label: 'Secrets', value: formatNumber(stats.value.secrets_total), icon: KeyRound, accent: 'red',
      sub: 'verschlüsselt at-rest' },
  ]
})

const accentColor: Record<string, string> = {
  sky: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
  green: 'bg-green-500/10 text-green-600 dark:text-green-400',
  amber: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  red: 'bg-red-500/10 text-red-600 dark:text-red-400',
}

const hostsByStatus = computed(() => {
  const groups: Record<string, Host[]> = {}
  for (const h of hosts.value) {
    const s = h.last_status || 'unknown'
    if (!groups[s]) groups[s] = []
    groups[s].push(h)
  }
  return groups
})

const appsGrouped = computed(() => {
  const groups: Record<string, App[]> = {}
  for (const a of apps.value) {
    const k = a.host_name
    if (!groups[k]) groups[k] = []
    groups[k].push(a)
  }
  return groups
})
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <div v-if="loading && !stats" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Dashboard...</div>
    <div v-else-if="error" class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 p-4 text-red-800 dark:text-red-200 text-sm">
      <p class="font-semibold flex items-center gap-2"><AlertTriangle :size="16" /> Fehler beim Laden</p>
      <p class="mt-1">{{ error }}</p>
      <button class="mt-2 text-xs underline" @click="load">Erneut versuchen</button>
    </div>

    <template v-if="stats">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card v-for="s in heroStats" :key="s.label" :padded="true">
          <div class="flex items-start justify-between">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{{ s.label }}</p>
              <p class="mt-2 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">{{ s.value }}</p>
              <p class="text-xs text-slate-400 mt-1">{{ s.sub }}</p>
            </div>
            <div class="grid place-items-center h-9 w-9 rounded-lg" :class="accentColor[s.accent]">
              <component :is="s.icon" :size="16" />
            </div>
          </div>
        </Card>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Hosts" subtitle="Aktueller Zustand pro Host">
          <div v-if="!hosts.length" class="py-6"><EmptyState title="Keine Hosts" /></div>
          <div v-else class="space-y-2">
            <div v-for="h in hosts" :key="h.id" class="flex items-center justify-between gap-2 py-1.5 border-b border-slate-100 dark:border-slate-800/60 last:border-0">
              <div class="min-w-0">
                <p class="font-medium text-sm text-slate-900 dark:text-slate-100">{{ h.name }} <span class="text-xs font-mono text-slate-400">{{ h.tailscale_ip }}</span></p>
                <p class="text-[11px] text-slate-400 truncate">{{ h.description || '—' }}</p>
              </div>
              <Badge :variant="statusVariant(h.last_status) as any" dot>{{ h.last_status }}</Badge>
            </div>
          </div>
        </Card>

        <Card title="Apps pro Host" subtitle="Deployment-Übersicht" class="lg:col-span-2">
          <div v-if="!apps.length" class="py-6"><EmptyState title="Keine Apps registriert" /></div>
          <div v-else class="space-y-4">
            <div v-for="(group, host) in appsGrouped" :key="host">
              <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
                <Server :size="12" /> {{ host }}
              </p>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div v-for="a in group" :key="a.id"
                  class="flex items-center justify-between gap-2 px-3 py-2 rounded-md border border-slate-200/70 dark:border-slate-800/70 bg-white/40 dark:bg-slate-900/40">
                  <div class="min-w-0">
                    <p class="font-medium text-sm text-slate-900 dark:text-slate-100 truncate">{{ a.name }}</p>
                    <p class="text-[11px] text-slate-400">{{ a.healthy_count }}/{{ a.container_count }} container</p>
                  </div>
                  <Badge :variant="statusVariant(a.last_status) as any" dot>{{ a.last_status }}</Badge>
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card title="Letzte Audit-Events" subtitle="Mutierende Aktionen">
        <div v-if="!stats.recent_audit?.length" class="py-6">
          <EmptyState title="Noch keine Aktionen" message="Mutierende Aktionen werden hier protokolliert." />
        </div>
        <div v-else class="space-y-1.5">
          <div v-for="e in stats.recent_audit" :key="e.id"
            class="flex items-center justify-between gap-3 py-1.5 border-b border-slate-100 dark:border-slate-800/60 last:border-0">
            <div class="flex items-center gap-2 min-w-0">
              <Badge variant="sky" dot>{{ e.action }}</Badge>
              <span class="font-mono text-xs text-slate-700 dark:text-slate-300 truncate">{{ e.target || '—' }}</span>
            </div>
            <p class="text-[11px] text-slate-400 tabular-nums">{{ relativeTime(e.ts) }}</p>
          </div>
        </div>
      </Card>
    </template>
  </div>
</template>
