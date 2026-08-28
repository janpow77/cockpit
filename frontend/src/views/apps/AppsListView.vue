<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, AppWindow, Edit2, Trash2, RefreshCw, RotateCcw, FileText } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Modal from '../../components/shared/Modal.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import ErrorState from '../../components/shared/ErrorState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { listApps, createApp, updateApp, deleteApp, restartApp, appHealthCheck, type AppCreate } from '../../api/apps'
import { listHosts } from '../../api/hosts'
import { useToastStore } from '../../stores/toast'
import { useConfirmStore } from '../../stores/confirm'
import { extractError } from '../../api/client'
import { relativeTime, statusVariant } from '../../utils/format'
import type { App, Host } from '../../api/types'

const toast = useToastStore()
const confirm = useConfirmStore()
const router = useRouter()

const apps = ref<App[]>([])
const hosts = ref<Host[]>([])
const loading = ref(true)
const fehler = ref<string | null>(null)
const speichern = ref(false)
const showModal = ref(false)
const editing = ref<App | null>(null)

const form = ref<AppCreate>({
  host_id: '', name: '', description: '', container_filter: '',
  compose_path: '', healthcheck_url: '', tags: [], enabled: true,
})

async function load() {
  loading.value = true
  fehler.value = null
  try {
    const [a, h] = await Promise.all([listApps(), listHosts()])
    apps.value = a
    hosts.value = h
  } catch (err) { fehler.value = extractError(err); toast.error(fehler.value) }
  finally { loading.value = false }
}
onMounted(load)

const grouped = computed(() => {
  const g: Record<string, App[]> = {}
  for (const a of apps.value) {
    const k = a.host_name
    if (!g[k]) g[k] = []
    g[k].push(a)
  }
  return g
})

function openCreate() {
  editing.value = null
  form.value = {
    host_id: hosts.value[0]?.id || '', name: '', description: '', container_filter: '',
    compose_path: '', healthcheck_url: '', tags: [], enabled: true,
  }
  showModal.value = true
}

function openEdit(a: App) {
  editing.value = a
  form.value = {
    host_id: a.host_id, name: a.name, description: a.description, container_filter: a.container_filter,
    compose_path: a.compose_path || '', healthcheck_url: a.healthcheck_url || '',
    tags: [...(a.tags || [])], enabled: a.enabled,
  }
  showModal.value = true
}

async function save() {
  if (speichern.value) return
  speichern.value = true
  try {
    if (editing.value) {
      await updateApp(editing.value.id, form.value)
      toast.success(`App '${form.value.name}' aktualisiert`)
    } else {
      await createApp(form.value)
      toast.success(`App '${form.value.name}' angelegt`)
    }
    showModal.value = false
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { speichern.value = false }
}

async function remove(a: App) {
  const ok = await confirm.ask({ title: `App '${a.name}' loeschen?`, message: 'Wird nur aus dem Cockpit entfernt — Container bleiben unberuehrt.', danger: true, confirmText: 'Loeschen' })
  if (!ok) return
  try { await deleteApp(a.id); toast.success('App geloescht'); await load() }
  catch (err) { toast.error(extractError(err)) }
}

async function refresh(a: App) {
  try { await appHealthCheck(a.id); await load() } catch (err) { toast.error(extractError(err)) }
}

async function doRestart(a: App) {
  const ok = await confirm.ask({ title: `App '${a.name}' neustarten?`, message: `docker compose restart auf ${a.host_name}. Bei Production-Apps NICHT leichtfertig.`, danger: true, confirmText: 'Neustarten' })
  if (!ok) return
  try {
    const r = await restartApp(a.id)
    if (r.ok) toast.success(`Restart von '${a.name}' ok`)
    else toast.error(`Restart fehlgeschlagen: ${r.error}`)
    await load()
  } catch (err) { toast.error(extractError(err)) }
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Apps" subtitle="Container-Stacks pro Host">
      <template #actions>
        <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-sm font-semibold" @click="openCreate">
          <Plus :size="14" /> App hinzufuegen
        </button>
      </template>

      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Apps...</div>
      <ErrorState v-else-if="fehler" title="Apps konnten nicht geladen werden" :message="fehler" @retry="load()" />
      <div v-else-if="!apps.length"><EmptyState title="Keine Apps" message="Registriere Container-Stacks fuer Health-Monitoring." /></div>
      <div v-else class="space-y-6">
        <div v-for="(group, hostName) in grouped" :key="hostName">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">{{ hostName }}</p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
                  <th class="py-2 pr-4">App</th>
                  <th class="py-2 pr-4">Filter</th>
                  <th class="py-2 pr-4">Container</th>
                  <th class="py-2 pr-4">Status</th>
                  <th class="py-2 pr-4">Letzter Check</th>
                  <th class="py-2 pr-2 text-right">Aktionen</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="a in group" :key="a.id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40">
                  <td class="py-2 pr-4">
                    <div class="flex items-center gap-2">
                      <AppWindow :size="14" class="text-slate-400" />
                      <button class="font-medium text-sky-600 dark:text-sky-400 hover:underline" @click="router.push(`/apps/${a.id}`)">{{ a.name }}</button>
                    </div>
                    <div class="flex flex-wrap gap-1 mt-0.5">
                      <Badge v-for="t in a.tags" :key="t" variant="slate">{{ t }}</Badge>
                    </div>
                  </td>
                  <td class="py-2 pr-4 font-mono text-xs text-slate-500">{{ a.container_filter || '—' }}</td>
                  <td class="py-2 pr-4 text-xs">
                    <span class="font-semibold tabular-nums">{{ a.healthy_count }}/{{ a.container_count }}</span> running
                  </td>
                  <td class="py-2 pr-4">
                    <Badge :variant="statusVariant(a.last_status) as any" dot>{{ a.last_status }}</Badge>
                  </td>
                  <td class="py-2 pr-4 text-xs text-slate-500">{{ relativeTime(a.last_check_at) }}</td>
                  <td class="py-2 pr-2">
                    <div class="flex items-center justify-end gap-1">
                      <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Logs" @click="router.push(`/apps/${a.id}`)">
                        <FileText :size="14" />
                      </button>
                      <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Health-Check" @click="refresh(a)">
                        <RefreshCw :size="14" />
                      </button>
                      <button class="rounded-md p-1.5 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/30" title="Restart" @click="doRestart(a)">
                        <RotateCcw :size="14" />
                      </button>
                      <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Bearbeiten" @click="openEdit(a)">
                        <Edit2 :size="14" />
                      </button>
                      <button class="rounded-md p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30" title="Loeschen" @click="remove(a)">
                        <Trash2 :size="14" />
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Card>

    <Modal :open="showModal" :title="editing ? 'App bearbeiten' : 'App hinzufuegen'" width="38rem" form-id="app-form" @close="showModal = false">
      <form id="app-form" class="space-y-3" @submit.prevent="save">
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Host</span>
          <select v-model="form.host_id" required class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm">
            <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.name }} ({{ h.tailscale_ip }})</option>
          </select>
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Name</span>
            <input v-model="form.name" required class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
          <label class="block">
            <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Container-Filter</span>
            <input v-model="form.container_filter" placeholder="name=auditworkshop-" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono" />
          </label>
        </div>
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Compose-Pfad</span>
          <input v-model="form.compose_path" placeholder="/opt/auditworkshop/compose.yaml" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono" />
        </label>
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Healthcheck-URL</span>
          <input v-model="form.healthcheck_url" placeholder="http://127.0.0.1:3004/" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
        </label>
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Beschreibung</span>
          <input v-model="form.description" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="form.enabled" type="checkbox" /> Enabled
        </label>
      </form>
      <template #footer="{ formId }">
        <button type="button" class="rounded-md px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="showModal = false">Abbrechen</button>
        <button type="submit" :form="formId" :disabled="speichern" class="rounded-md px-3 py-1.5 text-sm font-semibold bg-sky-600 hover:bg-sky-700 text-white disabled:opacity-50">Speichern</button>
      </template>
    </Modal>
  </div>
</template>
