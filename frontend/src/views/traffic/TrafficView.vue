<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Activity, Plus, Trash2, RefreshCw, AlertTriangle } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import ErrorState from '../../components/shared/ErrorState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import Modal from '../../components/shared/Modal.vue'
import Sparkline from '../../components/shared/Sparkline.vue'
import {
  listSources,
  createSource,
  deleteSource,
  collectNow,
  getSeries,
  type TrafficSourceCreate,
} from '../../api/traffic'
import { listHosts } from '../../api/hosts'
import { listApps } from '../../api/apps'
import { useToastStore } from '../../stores/toast'
import { useConfirmStore } from '../../stores/confirm'
import { usePollStore } from '../../stores/poll'
import { extractError } from '../../api/client'
import { relativeTime, statusVariant } from '../../utils/format'
import type {
  App,
  Host,
  TrafficBucketSize,
  TrafficSeries,
  TrafficSource,
} from '../../api/types'

const toast = useToastStore()
const confirm = useConfirmStore()
const poll = usePollStore()

const loading = ref(true)
const fehler = ref<string | null>(null)
const sources = ref<TrafficSource[]>([])
const hosts = ref<Host[]>([])
const apps = ref<App[]>([])

const showCreate = ref(false)
const form = ref<TrafficSourceCreate>({
  host_id: '',
  log_path: '/var/log/caddy/access.log',
  server_app_map: [],
  enabled: true,
})

// Series-Panel
const series = ref<TrafficSeries | null>(null)
const seriesLoading = ref(false)
const filterAppId = ref<string>('')
const filterHostId = ref<string>('')
const bucket = ref<TrafficBucketSize>('5m')
const zeitfenster = ref<string>('6h')

const requestsSeries = computed(() => series.value?.points.map((p) => p.requests) ?? [])
const errorSeries = computed(
  () => series.value?.points.map((p) => p.status_4xx + p.status_5xx) ?? [],
)
const latencySeries = computed(
  () => series.value?.points.map((p) => p.latency_p95_ms ?? 0) ?? [],
)
const errorRatePct = computed(() =>
  series.value ? Math.round(series.value.error_rate * 10000) / 100 : 0,
)

async function load() {
  loading.value = true
  fehler.value = null
  try {
    const [s, h, a] = await Promise.all([listSources(), listHosts(), listApps()])
    sources.value = s
    hosts.value = h
    apps.value = a
  } catch (err) {
    fehler.value = extractError(err)
    toast.error(fehler.value)
  } finally {
    loading.value = false
  }
}

async function loadSeries() {
  seriesLoading.value = true
  try {
    series.value = await getSeries({
      app_id: filterAppId.value || undefined,
      host_id: filterHostId.value || undefined,
      bucket: bucket.value,
      window: zeitfenster.value,
    })
  } catch (err) {
    toast.error(extractError(err))
  } finally {
    seriesLoading.value = false
  }
}

function openCreate() {
  form.value = {
    host_id: hosts.value[0]?.id || '',
    log_path: '/var/log/caddy/access.log',
    server_app_map: [],
    enabled: true,
  }
  showCreate.value = true
}

async function saveSource() {
  try {
    await createSource(form.value)
    toast.success('Traffic-Quelle angelegt')
    showCreate.value = false
    await load()
  } catch (err) {
    toast.error(extractError(err))
  }
}

async function removeSource(s: TrafficSource) {
  const ok = await confirm.ask({
    title: `Traffic-Quelle '${s.log_path}' loeschen?`,
    message: `Auf Host ${s.host_name}. Historische Samples bleiben erhalten.`,
    danger: true,
    confirmText: 'Loeschen',
  })
  if (!ok) return
  try {
    await deleteSource(s.id)
    toast.success('Traffic-Quelle entfernt')
    await load()
  } catch (err) {
    toast.error(extractError(err))
  }
}

async function triggerCollect() {
  try {
    const res = await collectNow()
    toast.success(`Sammellauf: ${res.ok}/${res.sources} ok, ${res.lines} Zeilen`)
    await load()
    await loadSeries()
  } catch (err) {
    toast.error(extractError(err))
  }
}

onMounted(async () => {
  await load()
  poll.start('traffic-series', loadSeries, 30_000)
})
onBeforeUnmount(() => {
  poll.stop('traffic-series')
})

watch([filterAppId, filterHostId, bucket, zeitfenster], loadSeries)

// Server-Name-Map-Editor: rudimentaer.
const newServerName = ref('')
const newAppName = ref('')

function addServerMap() {
  if (!newServerName.value || !newAppName.value) return
  form.value.server_app_map = [
    ...(form.value.server_app_map ?? []),
    { server_name: newServerName.value, app_name: newAppName.value },
  ]
  newServerName.value = ''
  newAppName.value = ''
}

function removeServerMap(idx: number) {
  form.value.server_app_map = (form.value.server_app_map ?? []).filter((_, i) => i !== idx)
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Traffic" subtitle="Live-Statistiken aus Caddy-Access-Logs">
      <template #actions>
        <button
          class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
          title="Sammellauf manuell triggern"
          @click="triggerCollect"
        >
          <RefreshCw :size="14" /> Jetzt sammeln
        </button>
        <button
          class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-sm font-semibold"
          @click="openCreate"
        >
          <Plus :size="14" /> Quelle anlegen
        </button>
      </template>

      <!-- Filter-Zeile -->
      <div class="flex flex-wrap items-center gap-3 mb-4 text-sm">
        <label class="flex items-center gap-1.5">
          <span class="text-slate-500">App:</span>
          <select
            v-model="filterAppId"
            class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1"
          >
            <option value="">— alle —</option>
            <option v-for="a in apps" :key="a.id" :value="a.id">{{ a.host_name }} / {{ a.name }}</option>
          </select>
        </label>
        <label class="flex items-center gap-1.5">
          <span class="text-slate-500">Host:</span>
          <select
            v-model="filterHostId"
            class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1"
          >
            <option value="">— alle —</option>
            <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.name }}</option>
          </select>
        </label>
        <label class="flex items-center gap-1.5">
          <span class="text-slate-500">Bucket:</span>
          <select
            v-model="bucket"
            class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1"
          >
            <option value="1m">1 min</option>
            <option value="5m">5 min</option>
            <option value="1h">1 h</option>
            <option value="1d">1 d</option>
          </select>
        </label>
        <label class="flex items-center gap-1.5">
          <span class="text-slate-500">Fenster:</span>
          <select
            v-model="zeitfenster"
            class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1"
          >
            <option value="30m">30 min</option>
            <option value="6h">6 h</option>
            <option value="24h">24 h</option>
            <option value="7d">7 d</option>
            <option value="30d">30 d</option>
          </select>
        </label>
        <span v-if="seriesLoading" class="text-xs text-slate-500"><Spinner /> aktualisiere…</span>
      </div>

      <!-- KPIs -->
      <div v-if="series" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <div class="rounded-md border border-slate-200 dark:border-slate-800 p-3">
          <p class="text-xs uppercase tracking-wider text-slate-500">Requests</p>
          <p class="text-2xl font-semibold tabular-nums">{{ series.total_requests.toLocaleString('de-DE') }}</p>
          <Sparkline
            class="mt-2 text-slate-400 dark:text-slate-600"
            :values="requestsSeries"
            :height="40"
            :width="240"
            stroke-color="#0284c7"
            fill-color="#0284c7"
          />
        </div>
        <div class="rounded-md border border-slate-200 dark:border-slate-800 p-3">
          <p class="text-xs uppercase tracking-wider text-slate-500">Fehler-Quote</p>
          <p
            class="text-2xl font-semibold tabular-nums"
            :class="errorRatePct >= 5 ? 'text-red-500' : (errorRatePct >= 1 ? 'text-amber-500' : '')"
          >
            {{ errorRatePct }} %
          </p>
          <Sparkline
            class="mt-2 text-slate-400 dark:text-slate-600"
            :values="errorSeries"
            :height="40"
            :width="240"
            stroke-color="#dc2626"
            fill-color="#dc2626"
          />
        </div>
        <div class="rounded-md border border-slate-200 dark:border-slate-800 p-3">
          <p class="text-xs uppercase tracking-wider text-slate-500">p95 Latenz</p>
          <p class="text-2xl font-semibold tabular-nums">
            {{ series.points.length ? Math.max(...series.points.map((p) => p.latency_p95_ms ?? 0)) : 0 }} <span class="text-sm text-slate-500">ms</span>
          </p>
          <Sparkline
            class="mt-2 text-slate-400 dark:text-slate-600"
            :values="latencySeries"
            :height="40"
            :width="240"
            stroke-color="#7c3aed"
          />
        </div>
        <div class="rounded-md border border-slate-200 dark:border-slate-800 p-3">
          <p class="text-xs uppercase tracking-wider text-slate-500">Zeitraum</p>
          <p class="text-sm mt-2 leading-tight">
            <span class="font-mono">{{ new Date(series.from_ts).toLocaleString('de-DE') }}</span>
            <br />
            <span class="text-slate-500">bis {{ new Date(series.to_ts).toLocaleString('de-DE') }}</span>
          </p>
          <p class="text-xs text-slate-500 mt-1">{{ series.points.length }} Buckets • {{ bucket }}</p>
        </div>
      </div>

      <ErrorState v-if="!loading && fehler" title="Traffic-Daten konnten nicht geladen werden" :message="fehler" @retry="load()" />
      <div v-else-if="!loading && !sources.length">
        <EmptyState
          title="Keine Traffic-Quellen"
          message="Pro Host eine Quelle anlegen (Pfad zur Caddy-access.log + Server-Name → App-Mapping)."
        />
      </div>
    </Card>

    <!-- Source-Liste -->
    <Card title="Quellen" subtitle="Caddy-Logs werden pro Minute gepollt">
      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Quellen…</div>
      <div v-else-if="sources.length" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
              <th class="py-2 pr-4">Host</th>
              <th class="py-2 pr-4">Logfile</th>
              <th class="py-2 pr-4">Server→App-Mapping</th>
              <th class="py-2 pr-4">Status</th>
              <th class="py-2 pr-4">Letzter Lauf</th>
              <th class="py-2 pr-2 text-right">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sources" :key="s.id" class="border-b border-slate-100 dark:border-slate-800/60">
              <td class="py-2 pr-4 font-medium">{{ s.host_name }}</td>
              <td class="py-2 pr-4 font-mono text-xs text-slate-600 dark:text-slate-400">{{ s.log_path }}</td>
              <td class="py-2 pr-4">
                <div v-if="s.server_app_map.length" class="flex flex-col gap-0.5">
                  <span v-for="m in s.server_app_map" :key="m.server_name" class="text-xs">
                    <span class="font-mono text-slate-500">{{ m.server_name }}</span>
                    <span class="text-slate-400"> → </span>
                    <span class="font-medium">{{ m.app_name }}</span>
                  </span>
                </div>
                <span v-else class="text-xs text-slate-400">— kein Mapping —</span>
              </td>
              <td class="py-2 pr-4">
                <Badge :variant="statusVariant(s.last_status) as any" dot>{{ s.last_status }}</Badge>
                <p v-if="s.last_error" class="text-xs text-red-500 mt-1 flex items-start gap-1">
                  <AlertTriangle :size="12" class="mt-0.5 flex-shrink-0" /> {{ s.last_error }}
                </p>
              </td>
              <td class="py-2 pr-4 text-xs text-slate-500">{{ relativeTime(s.last_collect_at) }}</td>
              <td class="py-2 pr-2 text-right">
                <button
                  class="rounded-md p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30"
                  title="Loeschen"
                  @click="removeSource(s)"
                >
                  <Trash2 :size="14" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- Create-Modal -->
    <Modal :open="showCreate" title="Traffic-Quelle anlegen" width="38rem" @close="showCreate = false">
      <form class="space-y-3" @submit.prevent="saveSource">
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Host</span>
          <select
            v-model="form.host_id"
            required
            class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
          >
            <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.name }} ({{ h.tailscale_ip }})</option>
          </select>
        </label>
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Caddy-Logfile (Pfad)</span>
          <input
            v-model="form.log_path"
            required
            placeholder="/var/log/caddy/access.log"
            class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono"
          />
          <p class="text-xs text-slate-500 mt-1">
            Caddy muss als JSON-Format loggen (<code>output file ... format json</code>). Cockpit liest inkrementell via SSH.
          </p>
        </label>

        <div>
          <p class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider mb-2">Server-Name → App-Mapping</p>
          <div v-for="(m, idx) in form.server_app_map" :key="idx" class="flex items-center gap-2 mb-1 text-sm">
            <span class="font-mono flex-1">{{ m.server_name }}</span>
            <span class="text-slate-400">→</span>
            <span class="flex-1 font-medium">{{ m.app_name }}</span>
            <button type="button" class="text-red-500 hover:text-red-700" @click="removeServerMap(idx)">
              <Trash2 :size="14" />
            </button>
          </div>
          <div class="flex items-center gap-2 mt-2">
            <input
              v-model="newServerName"
              placeholder="workshop.flowaudit.de"
              class="flex-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1 text-sm font-mono"
            />
            <span class="text-slate-400">→</span>
            <select
              v-model="newAppName"
              class="flex-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1 text-sm"
            >
              <option value="">— App waehlen —</option>
              <option v-for="a in apps" :key="a.id" :value="a.name">{{ a.name }} ({{ a.host_name }})</option>
            </select>
            <button
              type="button"
              class="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-1 text-sm"
              @click="addServerMap"
            >
              <Plus :size="14" />
            </button>
          </div>
        </div>

        <label class="flex items-center gap-2 text-sm pt-2">
          <input v-model="form.enabled" type="checkbox" /> Aktiv (wird vom Collector berücksichtigt)
        </label>
      </form>
      <template #footer>
        <button class="rounded-md px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="showCreate = false">
          Abbrechen
        </button>
        <button class="rounded-md px-3 py-1.5 text-sm font-semibold bg-sky-600 hover:bg-sky-700 text-white" @click="saveSource">
          Anlegen
        </button>
      </template>
    </Modal>
  </div>
</template>
