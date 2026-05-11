<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus, KeyRound, Eye, EyeOff, Edit2, Trash2, Copy, AlertTriangle } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Modal from '../../components/shared/Modal.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { listSecrets, createSecret, updateSecret, deleteSecret, revealSecret, type SecretCreate } from '../../api/secrets'
import { useToastStore } from '../../stores/toast'
import { useConfirmStore } from '../../stores/confirm'
import { extractError } from '../../api/client'
import { relativeTime } from '../../utils/format'
import type { Secret } from '../../api/types'

const toast = useToastStore()
const confirm = useConfirmStore()

const secrets = ref<Secret[]>([])
const loading = ref(true)
const showModal = ref(false)
const editing = ref<Secret | null>(null)

const form = ref<SecretCreate>({
  key: '', value: '', app_tag: '', host_tag: '', comment: '',
})

const revealModal = ref<{ open: boolean; secret: Secret | null; purpose: string; value: string | null; loading: boolean }>({
  open: false, secret: null, purpose: '', value: null, loading: false,
})

async function load() {
  loading.value = true
  try { secrets.value = await listSecrets() } catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}
onMounted(load)

function openCreate() {
  editing.value = null
  form.value = { key: '', value: '', app_tag: '', host_tag: '', comment: '' }
  showModal.value = true
}

function openEdit(s: Secret) {
  editing.value = s
  form.value = { key: s.key, value: '', app_tag: s.app_tag || '', host_tag: s.host_tag || '', comment: s.comment }
  showModal.value = true
}

async function save() {
  try {
    if (editing.value) {
      const patch: any = {
        app_tag: form.value.app_tag || null,
        host_tag: form.value.host_tag || null,
        comment: form.value.comment,
      }
      if (form.value.value) patch.value = form.value.value
      await updateSecret(editing.value.id, patch)
      toast.success('Secret aktualisiert')
    } else {
      await createSecret(form.value)
      toast.success(`Secret '${form.value.key}' angelegt`)
    }
    showModal.value = false
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function remove(s: Secret) {
  const ok = await confirm.ask({
    title: `Secret '${s.key}' loeschen?`,
    message: 'Der Wert ist verschluesselt — nach dem Loeschen unwiederbringlich verloren.',
    danger: true, confirmText: 'Loeschen',
  })
  if (!ok) return
  try { await deleteSecret(s.id); toast.success('Geloescht'); await load() }
  catch (err) { toast.error(extractError(err)) }
}

function openReveal(s: Secret) {
  revealModal.value = { open: true, secret: s, purpose: '', value: null, loading: false }
}

async function doReveal() {
  if (!revealModal.value.secret) return
  if (!revealModal.value.purpose.trim()) { toast.warning('Begruendung ist Pflicht'); return }
  revealModal.value.loading = true
  try {
    const r = await revealSecret(revealModal.value.secret.id, revealModal.value.purpose)
    revealModal.value.value = r.value
    toast.success('Reveal protokolliert')
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { revealModal.value.loading = false }
}

async function copyValue() {
  if (!revealModal.value.value) return
  try { await navigator.clipboard.writeText(revealModal.value.value); toast.success('In Zwischenablage kopiert') }
  catch { toast.error('Clipboard nicht verfuegbar') }
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Secrets / Vault" subtitle="Werte sind verschluesselt at-rest. Reveal benoetigt Begruendung.">
      <template #actions>
        <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-sm font-semibold" @click="openCreate">
          <Plus :size="14" /> Secret
        </button>
      </template>

      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Secrets...</div>
      <div v-else-if="!secrets.length"><EmptyState title="Keine Secrets" message="Lege Tokens, API-Keys, Passwoerter zentral an." /></div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
            <th class="py-2 pr-4">Key</th>
            <th class="py-2 pr-4">Tags</th>
            <th class="py-2 pr-4">Reveals</th>
            <th class="py-2 pr-4">Letzte Verwendung</th>
            <th class="py-2 pr-2 text-right">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in secrets" :key="s.id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40">
            <td class="py-2 pr-4">
              <div class="flex items-center gap-2">
                <KeyRound :size="14" class="text-slate-400" />
                <span class="font-mono font-medium">{{ s.key }}</span>
              </div>
              <p v-if="s.comment" class="text-[11px] text-slate-400 mt-0.5">{{ s.comment }}</p>
            </td>
            <td class="py-2 pr-4">
              <div class="flex gap-1 flex-wrap">
                <Badge v-if="s.app_tag" variant="sky">app:{{ s.app_tag }}</Badge>
                <Badge v-if="s.host_tag" variant="amber">host:{{ s.host_tag }}</Badge>
              </div>
            </td>
            <td class="py-2 pr-4 text-xs tabular-nums">{{ s.reveal_count }}</td>
            <td class="py-2 pr-4 text-xs text-slate-500" :title="s.last_used_purpose || ''">{{ relativeTime(s.last_used_at) }}</td>
            <td class="py-2 pr-2">
              <div class="flex items-center justify-end gap-1">
                <button class="rounded-md p-1.5 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/30" title="Wert anzeigen" @click="openReveal(s)">
                  <Eye :size="14" />
                </button>
                <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Bearbeiten" @click="openEdit(s)">
                  <Edit2 :size="14" />
                </button>
                <button class="rounded-md p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30" title="Loeschen" @click="remove(s)">
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </Card>

    <Modal :open="showModal" :title="editing ? `Secret '${editing.key}' bearbeiten` : 'Secret hinzufuegen'" @close="showModal = false">
      <form class="space-y-3" @submit.prevent="save">
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Key</span>
          <input v-model="form.key" required :disabled="!!editing" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 disabled:bg-slate-100 dark:disabled:bg-slate-800 px-3 py-2 text-sm font-mono" />
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">{{ editing ? 'Neuer Wert (leer = unveraendert)' : 'Wert' }}</span>
          <input v-model="form.value" :required="!editing" type="password" placeholder="••••••••" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono" />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">App-Tag</span>
            <input v-model="form.app_tag" placeholder="audit_designer" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Host-Tag</span>
            <input v-model="form.host_tag" placeholder="ccx23" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
        </div>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Kommentar</span>
          <input v-model="form.comment" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
        </label>
      </form>
      <template #footer>
        <button class="rounded-md px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="showModal = false">Abbrechen</button>
        <button class="rounded-md px-3 py-1.5 text-sm font-semibold bg-sky-600 hover:bg-sky-700 text-white" @click="save">Speichern</button>
      </template>
    </Modal>

    <Modal :open="revealModal.open" :title="`Secret '${revealModal.secret?.key}' anzeigen`" @close="revealModal.open = false">
      <div v-if="!revealModal.value" class="space-y-3">
        <div class="flex gap-3">
          <AlertTriangle :size="20" class="text-amber-500 shrink-0 mt-0.5" />
          <p class="text-sm text-slate-700 dark:text-slate-300">Reveal-Aktionen werden mit Begruendung im Audit-Log protokolliert.</p>
        </div>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Begruendung (Pflicht)</span>
          <textarea v-model="revealModal.purpose" rows="3" required placeholder="z.B. 'Audit-Designer-Deploy auf NUC, Token-Rotation'" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"></textarea>
        </label>
      </div>
      <div v-else class="space-y-3">
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-500">Wert</p>
        <pre class="bg-slate-950 text-green-300 p-3 rounded-md text-xs font-mono overflow-x-auto break-all whitespace-pre-wrap">{{ revealModal.value }}</pre>
      </div>
      <template #footer>
        <button class="rounded-md px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="revealModal.open = false">Schliessen</button>
        <button v-if="revealModal.value" class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold bg-slate-600 hover:bg-slate-700 text-white" @click="copyValue">
          <Copy :size="14" /> In Zwischenablage
        </button>
        <button v-else class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold bg-amber-600 hover:bg-amber-700 text-white" :disabled="revealModal.loading" @click="doReveal">
          <Spinner v-if="revealModal.loading" :size="14" />
          <Eye v-else :size="14" /> Anzeigen + protokollieren
        </button>
      </template>
    </Modal>
  </div>
</template>
