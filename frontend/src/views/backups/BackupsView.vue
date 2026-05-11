<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus, Database, Edit2, Trash2, Play, FileText } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Modal from '../../components/shared/Modal.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { listBackups, createBackup, updateBackup, deleteBackup, runBackup, type BackupCreate } from '../../api/backups'
import { listHosts } from '../../api/hosts'
import { useToastStore } from '../../stores/toast'
import { useConfirmStore } from '../../stores/confirm'
import { extractError } from '../../api/client'
import { formatBytes, relativeTime, statusVariant } from '../../utils/format'
import type { Backup, Host } from '../../api/types'

const toast = useToastStore()
const confirm = useConfirmStore()

const backups = ref<Backup[]>([])
const hosts = ref<Host[]>([])
const loading = ref(true)
const showModal = ref(false)
const editing = ref<Backup | null>(null)
const lastRunResult = ref<{ name: string; ok: boolean; log: string; error?: string | null } | null>(null)

const form = ref<BackupCreate>({
  name: '', host_id: '', backup_type: 'shell',
  command: '', target_path: '', schedule_cron: '', enabled: true,
})

async function load() {
  loading.value = true
  try {
    const [b, h] = await Promise.all([listBackups(), listHosts()])
    backups.value = b
    hosts.value = h
  } catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}
onMounted(load)

function openCreate() {
  editing.value = null
  form.value = {
    name: '', host_id: hosts.value[0]?.id || '', backup_type: 'shell',
    command: '', target_path: '', schedule_cron: '', enabled: true,
  }
  showModal.value = true
}

function openEdit(b: Backup) {
  editing.value = b
  form.value = {
    name: b.name, host_id: b.host_id, backup_type: b.backup_type as any,
    command: b.command, target_path: b.target_path,
    schedule_cron: b.schedule_cron || '', enabled: b.enabled,
  }
  showModal.value = true
}

async function save() {
  try {
    if (editing.value) {
      await updateBackup(editing.value.id, form.value)
      toast.success('Backup aktualisiert')
    } else {
      await createBackup(form.value)
      toast.success('Backup angelegt')
    }
    showModal.value = false
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function remove(b: Backup) {
  const ok = await confirm.ask({ title: `Backup-Job '${b.name}' loeschen?`, message: 'Backup-Daten bleiben unberuehrt — nur der Job wird entfernt.', danger: true })
  if (!ok) return
  try { await deleteBackup(b.id); toast.success('Geloescht'); await load() }
  catch (err) { toast.error(extractError(err)) }
}

async function doRun(b: Backup) {
  const ok = await confirm.ask({
    title: `Backup '${b.name}' jetzt ausfuehren?`,
    message: `Fuehrt: ${b.command.slice(0, 100)}${b.command.length > 100 ? '...' : ''}`,
    confirmText: 'Ausfuehren',
  })
  if (!ok) return
  try {
    const r = await runBackup(b.id)
    lastRunResult.value = { name: b.name, ok: r.ok, log: r.log, error: r.error }
    if (r.ok) toast.success(`Backup '${b.name}' ok (${formatBytes(r.bytes)})`)
    else toast.error(`Backup fehlgeschlagen: ${r.error}`)
    await load()
  } catch (err) { toast.error(extractError(err)) }
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Backups" subtitle="Registrierte Jobs — werden auf dem jeweiligen Host ausgefuehrt">
      <template #actions>
        <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-sm font-semibold" @click="openCreate">
          <Plus :size="14" /> Backup-Job
        </button>
      </template>

      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Backups...</div>
      <div v-else-if="!backups.length"><EmptyState title="Keine Backup-Jobs" message="Lege deinen ersten Postgres- oder rsync-Job an." /></div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
            <th class="py-2 pr-4">Job</th>
            <th class="py-2 pr-4">Host</th>
            <th class="py-2 pr-4">Typ</th>
            <th class="py-2 pr-4">Letzter Run</th>
            <th class="py-2 pr-4">Groesse</th>
            <th class="py-2 pr-4">Cron</th>
            <th class="py-2 pr-2 text-right">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in backups" :key="b.id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40">
            <td class="py-2 pr-4">
              <div class="flex items-center gap-2">
                <Database :size="14" class="text-slate-400" />
                <span class="font-medium">{{ b.name }}</span>
              </div>
              <p class="text-[11px] text-slate-400 font-mono truncate max-w-md">{{ b.target_path }}</p>
            </td>
            <td class="py-2 pr-4 text-xs">{{ b.host_name }}</td>
            <td class="py-2 pr-4"><Badge variant="slate">{{ b.backup_type }}</Badge></td>
            <td class="py-2 pr-4">
              <Badge :variant="statusVariant(b.last_run_status) as any" dot>{{ b.last_run_status }}</Badge>
              <p class="text-[10px] text-slate-400 mt-0.5">{{ relativeTime(b.last_run_at) }}</p>
            </td>
            <td class="py-2 pr-4 text-xs tabular-nums">{{ formatBytes(b.last_size_bytes) }}</td>
            <td class="py-2 pr-4 text-xs font-mono text-slate-500">{{ b.schedule_cron || '—' }}</td>
            <td class="py-2 pr-2">
              <div class="flex items-center justify-end gap-1">
                <button class="rounded-md p-1.5 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30" title="Jetzt ausfuehren" @click="doRun(b)">
                  <Play :size="14" />
                </button>
                <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Bearbeiten" @click="openEdit(b)">
                  <Edit2 :size="14" />
                </button>
                <button class="rounded-md p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30" title="Loeschen" @click="remove(b)">
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </Card>

    <Card v-if="lastRunResult" :title="`Letzter Run: ${lastRunResult.name}`" :subtitle="lastRunResult.ok ? 'erfolgreich' : 'fehlgeschlagen'">
      <pre class="bg-slate-950 text-green-300 p-3 rounded-md text-[11px] font-mono overflow-x-auto max-h-96 overflow-y-auto whitespace-pre-wrap">{{ lastRunResult.log || '(kein Output)' }}</pre>
      <p v-if="lastRunResult.error" class="mt-2 text-xs text-red-500">{{ lastRunResult.error }}</p>
    </Card>

    <Modal :open="showModal" :title="editing ? 'Backup bearbeiten' : 'Backup-Job anlegen'" width="40rem" @close="showModal = false">
      <form class="space-y-3" @submit.prevent="save">
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Name</span>
            <input v-model="form.name" required class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Host</span>
            <select v-model="form.host_id" required class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm">
              <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.name }}</option>
            </select>
          </label>
        </div>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Typ</span>
          <select v-model="form.backup_type" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm">
            <option value="postgres">postgres</option>
            <option value="rsync">rsync</option>
            <option value="docker_volume">docker_volume</option>
            <option value="shell">shell</option>
          </select>
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Command</span>
          <textarea v-model="form.command" required rows="3" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-xs font-mono"></textarea>
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Target-Pfad</span>
            <input v-model="form.target_path" required placeholder="/backups/foo.sql.gz" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono" />
          </label>
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Cron (informativ)</span>
            <input v-model="form.schedule_cron" placeholder="0 2 * * *" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono" />
          </label>
        </div>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="form.enabled" type="checkbox" /> Enabled
        </label>
      </form>
      <template #footer>
        <button class="rounded-md px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="showModal = false">Abbrechen</button>
        <button class="rounded-md px-3 py-1.5 text-sm font-semibold bg-sky-600 hover:bg-sky-700 text-white" @click="save">Speichern</button>
      </template>
    </Modal>
  </div>
</template>
