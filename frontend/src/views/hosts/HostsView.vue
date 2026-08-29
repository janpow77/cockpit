<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus, Server, Wifi, WifiOff, Edit2, Trash2, RefreshCw } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Modal from '../../components/shared/Modal.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import ErrorState from '../../components/shared/ErrorState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { listHosts, createHost, updateHost, deleteHost, checkHost, type HostCreate } from '../../api/hosts'
import { useToastStore } from '../../stores/toast'
import { useConfirmStore } from '../../stores/confirm'
import { extractError } from '../../api/client'
import { formatDateTime, relativeTime, statusVariant } from '../../utils/format'
import type { Host } from '../../api/types'

const toast = useToastStore()
const confirm = useConfirmStore()

const hosts = ref<Host[]>([])
const loading = ref(true)
const fehler = ref<string | null>(null)
const speichern = ref(false)
const showModal = ref(false)
const editing = ref<Host | null>(null)

const form = ref<HostCreate>({
  name: '', tailscale_ip: '', description: '', ssh_user: 'janpow',
  ssh_key_path: '/root/.ssh/cockpit_id_ed25519', is_self: false, enabled: true,
})

async function load() {
  loading.value = true
  fehler.value = null
  try { hosts.value = await listHosts() } catch (err) { fehler.value = extractError(err); toast.error(fehler.value) }
  finally { loading.value = false }
}
onMounted(load)

function openCreate() {
  editing.value = null
  form.value = {
    name: '', tailscale_ip: '', description: '', ssh_user: 'janpow',
    ssh_key_path: '/root/.ssh/cockpit_id_ed25519', is_self: false, enabled: true,
  }
  showModal.value = true
}

function openEdit(host: Host) {
  editing.value = host
  form.value = {
    name: host.name, tailscale_ip: host.tailscale_ip, description: host.description,
    ssh_user: host.ssh_user, ssh_key_path: host.ssh_key_path,
    is_self: host.is_self, enabled: host.enabled,
  }
  showModal.value = true
}

async function save() {
  if (speichern.value) return
  speichern.value = true
  try {
    if (editing.value) {
      await updateHost(editing.value.id, form.value)
      toast.success(`Host '${form.value.name}' aktualisiert`)
    } else {
      await createHost(form.value)
      toast.success(`Host '${form.value.name}' angelegt`)
    }
    showModal.value = false
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { speichern.value = false }
}

async function removeHost(host: Host) {
  const ok = await confirm.ask({
    title: `Host '${host.name}' loeschen?`,
    message: 'Alle zugeordneten Apps und Backups werden ebenfalls geloescht.',
    confirmText: 'Loeschen', danger: true,
  })
  if (!ok) return
  try { await deleteHost(host.id); toast.success('Host geloescht'); await load() }
  catch (err) { toast.error(extractError(err)) }
}

async function refresh(host: Host) {
  try {
    await checkHost(host.id)
    toast.success(`Health-Check ${host.name} ok`)
    await load()
  } catch (err) { toast.error(extractError(err)) }
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Hosts" subtitle="Tailscale-Knoten im Cockpit-Verbund">
      <template #actions>
        <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-sm font-semibold" @click="openCreate">
          <Plus :size="14" /> Host hinzufuegen
        </button>
      </template>

      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Hosts...</div>
      <ErrorState v-else-if="fehler" title="Hosts konnten nicht geladen werden" :message="fehler" @retry="load()" />
      <div v-else-if="!hosts.length"><EmptyState title="Keine Hosts" message="Lege NUC, evo, MacBook etc. an." /></div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
              <th class="py-2 pr-4">Name</th>
              <th class="py-2 pr-4">Tailscale IP</th>
              <th class="py-2 pr-4">SSH</th>
              <th class="py-2 pr-4">Status</th>
              <th class="py-2 pr-4">Letzter Check</th>
              <th class="py-2 pr-2 text-right">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in hosts" :key="h.id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40">
              <td class="py-2 pr-4">
                <div class="flex items-center gap-2">
                  <Server :size="14" class="text-slate-400" />
                  <div>
                    <p class="font-medium text-slate-900 dark:text-slate-100">{{ h.name }} <span v-if="h.is_self" class="ml-1 text-[10px] uppercase font-semibold text-sky-600">self</span></p>
                    <p class="text-[11px] text-slate-400">{{ h.description || '—' }}</p>
                  </div>
                </div>
              </td>
              <td class="py-2 pr-4 font-mono text-xs">{{ h.tailscale_ip }}</td>
              <td class="py-2 pr-4 text-xs text-slate-500">{{ h.ssh_user || '—' }}@... <span v-if="h.ssh_key_path" class="ml-1">key</span></td>
              <td class="py-2 pr-4">
                <Badge :variant="statusVariant(h.last_status) as any" dot>
                  <Wifi v-if="h.last_status === 'online'" :size="10" />
                  <WifiOff v-else :size="10" />
                  {{ h.last_status }}
                </Badge>
                <p v-if="h.last_error" class="text-[10px] text-red-500 mt-0.5 truncate max-w-xs">{{ h.last_error }}</p>
              </td>
              <td class="py-2 pr-4 text-xs text-slate-500" :title="formatDateTime(h.last_check_at)">{{ relativeTime(h.last_check_at) }}</td>
              <td class="py-2 pr-2">
                <div class="flex items-center justify-end gap-1">
                  <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Health-Check" @click="refresh(h)">
                    <RefreshCw :size="14" />
                  </button>
                  <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Bearbeiten" @click="openEdit(h)">
                    <Edit2 :size="14" />
                  </button>
                  <button class="rounded-md p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30" title="Loeschen" @click="removeHost(h)">
                    <Trash2 :size="14" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <Modal :open="showModal" :title="editing ? 'Host bearbeiten' : 'Host hinzufuegen'" form-id="host-form" @close="showModal = false">
      <form id="host-form" class="space-y-3" @submit.prevent="save">
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Name</span>
          <input v-model="form.name" required class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
        </label>
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Tailscale IP</span>
          <input v-model="form.tailscale_ip" required placeholder="100.x.y.z" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono" />
        </label>
        <label class="block">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Beschreibung</span>
          <input v-model="form.description" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">SSH-User</span>
            <input v-model="form.ssh_user" placeholder="janpow / deploy / root" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
          <label class="block">
            <span class="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">SSH-Key-Pfad</span>
            <input v-model="form.ssh_key_path" placeholder="/root/.ssh/cockpit_id_ed25519" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
        </div>
        <div class="flex items-center gap-4">
          <label class="flex items-center gap-2 text-sm">
            <input v-model="form.is_self" type="checkbox" /> Self-Host (kein SSH)
          </label>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="form.enabled" type="checkbox" /> Enabled
          </label>
        </div>
      </form>
      <template #footer="{ formId }">
        <button type="button" class="rounded-md px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="showModal = false">Abbrechen</button>
        <button type="submit" :form="formId" :disabled="speichern" class="rounded-md px-3 py-1.5 text-sm font-semibold bg-sky-600 hover:bg-sky-700 text-white disabled:opacity-50">Speichern</button>
      </template>
    </Modal>
  </div>
</template>
