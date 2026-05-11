<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCw, RotateCcw, FileText, Container } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { getApp, restartApp, appHealthCheck, appLogs } from '../../api/apps'
import { useToastStore } from '../../stores/toast'
import { useConfirmStore } from '../../stores/confirm'
import { extractError } from '../../api/client'
import { statusVariant, formatDateTime } from '../../utils/format'
import type { AppDetail } from '../../api/types'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()
const confirm = useConfirmStore()

const app = ref<AppDetail | null>(null)
const loading = ref(true)
const logs = ref<string>('')
const logsLoading = ref(false)
const tail = ref(200)

async function load() {
  loading.value = true
  try { app.value = await getApp(String(route.params.id)) }
  catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}

async function loadLogs() {
  if (!app.value) return
  logsLoading.value = true
  try {
    const r = await appLogs(app.value.id, tail.value)
    logs.value = r.logs
  } catch (err) { toast.error(extractError(err)) }
  finally { logsLoading.value = false }
}

async function refresh() {
  if (!app.value) return
  try { await appHealthCheck(app.value.id); await load() } catch (err) { toast.error(extractError(err)) }
}

async function doRestart() {
  if (!app.value) return
  const ok = await confirm.ask({
    title: `App '${app.value.name}' neustarten?`,
    message: `docker compose restart auf ${app.value.host_name}.`,
    danger: true, confirmText: 'Neustarten',
  })
  if (!ok) return
  try {
    const r = await restartApp(app.value.id)
    if (r.ok) toast.success('Restart ok')
    else toast.error('Restart fehlgeschlagen: ' + r.error)
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

onMounted(load)
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <button class="inline-flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-400 hover:text-sky-600" @click="router.back()">
      <ArrowLeft :size="14" /> Zurueck zur Liste
    </button>

    <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade App-Details...</div>
    <template v-else-if="app">
      <Card>
        <div class="flex items-start justify-between gap-4">
          <div>
            <h1 class="text-xl font-bold text-slate-900 dark:text-slate-100">{{ app.name }}</h1>
            <p class="text-sm text-slate-500 mt-1">auf <span class="font-semibold">{{ app.host_name }}</span> · {{ app.description || 'keine Beschreibung' }}</p>
            <div class="flex gap-2 mt-2">
              <Badge :variant="statusVariant(app.last_status) as any" dot>{{ app.last_status }}</Badge>
              <Badge variant="slate">{{ app.healthy_count }}/{{ app.container_count }} running</Badge>
              <Badge v-for="t in app.tags" :key="t" variant="sky">{{ t }}</Badge>
            </div>
          </div>
          <div class="flex gap-2">
            <button class="inline-flex items-center gap-1.5 rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800" @click="refresh">
              <RefreshCw :size="14" /> Health-Check
            </button>
            <button class="inline-flex items-center gap-1.5 rounded-md bg-amber-600 hover:bg-amber-700 text-white px-3 py-1.5 text-sm font-semibold" @click="doRestart">
              <RotateCcw :size="14" /> Restart
            </button>
          </div>
        </div>
      </Card>

      <Card title="Container">
        <div v-if="!app.containers?.length" class="text-sm text-slate-500">Keine Container gefunden mit Filter <code class="font-mono text-xs bg-slate-100 dark:bg-slate-800 px-1 rounded">{{ app.container_filter }}</code>.</div>
        <table v-else class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
              <th class="py-2 pr-4">Name</th>
              <th class="py-2 pr-4">Image</th>
              <th class="py-2 pr-4">State</th>
              <th class="py-2 pr-4">Status</th>
              <th class="py-2 pr-4">Ports</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in app.containers" :key="c.name" class="border-b border-slate-100 dark:border-slate-800/60">
              <td class="py-2 pr-4 font-mono text-xs"><Container :size="12" class="inline mr-1 text-slate-400" />{{ c.name }}</td>
              <td class="py-2 pr-4 font-mono text-xs text-slate-500">{{ c.image }}</td>
              <td class="py-2 pr-4"><Badge :variant="statusVariant(c.state) as any" dot>{{ c.state }}</Badge></td>
              <td class="py-2 pr-4 text-xs text-slate-500 truncate max-w-xs">{{ c.status }}</td>
              <td class="py-2 pr-4 text-xs font-mono text-slate-500 truncate max-w-xs">{{ c.ports || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </Card>

      <Card title="Logs" subtitle="docker compose logs / docker logs">
        <template #actions>
          <select v-model.number="tail" class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1 text-xs">
            <option :value="50">50</option>
            <option :value="200">200</option>
            <option :value="500">500</option>
            <option :value="1000">1000</option>
          </select>
          <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-xs font-semibold" @click="loadLogs">
            <FileText :size="12" /> Laden
          </button>
        </template>
        <div v-if="logsLoading" class="flex items-center gap-2 text-slate-500 py-3"><Spinner /> Lade Logs...</div>
        <pre v-else-if="logs" class="bg-slate-950 text-green-300 p-3 rounded-md text-[11px] font-mono overflow-x-auto max-h-[600px] overflow-y-auto whitespace-pre-wrap">{{ logs }}</pre>
        <p v-else class="text-sm text-slate-500">Logs noch nicht geladen.</p>
      </Card>

      <Card title="Metadaten">
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
          <dt class="text-slate-500">Container-Filter</dt><dd class="font-mono">{{ app.container_filter || '—' }}</dd>
          <dt class="text-slate-500">Compose-Pfad</dt><dd class="font-mono">{{ app.compose_path || '—' }}</dd>
          <dt class="text-slate-500">Healthcheck-URL</dt><dd class="font-mono">{{ app.healthcheck_url || '—' }}</dd>
          <dt class="text-slate-500">Letzter Check</dt><dd>{{ formatDateTime(app.last_check_at) }}</dd>
          <dt class="text-slate-500">Erstellt</dt><dd>{{ formatDateTime(app.created_at) }}</dd>
          <dt class="text-slate-500">Aktualisiert</dt><dd>{{ formatDateTime(app.updated_at) }}</dd>
        </dl>
      </Card>
    </template>
  </div>
</template>
