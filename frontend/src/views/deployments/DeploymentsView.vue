<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { History, GitCommit, Package, Clock } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { listRecent } from '../../api/deployments'
import { useToastStore } from '../../stores/toast'
import { extractError } from '../../api/client'
import { relativeTime } from '../../utils/format'
import type { Deployment } from '../../api/types'

const toast = useToastStore()
const router = useRouter()
const loading = ref(true)
const items = ref<Deployment[]>([])

async function load() {
  loading.value = true
  try {
    items.value = await listRecent(100)
  } catch (err) {
    toast.error(extractError(err))
  } finally {
    loading.value = false
  }
}

onMounted(load)

function shortDigest(d: string | null): string {
  if (!d) return ''
  return d.length > 19 ? d.slice(0, 19) + '…' : d
}

function statusVariant(s: string): 'success' | 'warning' | 'error' | 'slate' {
  if (s === 'ok') return 'success'
  if (s === 'started') return 'warning'
  if (s === 'failed') return 'error'
  return 'slate'
}

function sourceVariant(s: string): 'slate' | 'sky' | 'amber' {
  if (s === 'gh-action') return 'sky'
  if (s === 'manual') return 'amber'
  return 'slate'
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Deployments" subtitle="Letzte Image-Aktivierungen pro App, host-uebergreifend">
      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Historie…</div>
      <EmptyState
        v-else-if="!items.length"
        title="Noch keine Deployments protokolliert"
        message="Lifecycle-Skripte koennen Deployments per X-Lifecycle-Token an /admin/api/apps/{id}/deployments melden."
      />
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
              <th class="py-2 pr-4">Zeit</th>
              <th class="py-2 pr-4">App</th>
              <th class="py-2 pr-4">Image</th>
              <th class="py-2 pr-4">Git-SHA</th>
              <th class="py-2 pr-4">Quelle</th>
              <th class="py-2 pr-4">Status</th>
              <th class="py-2 pr-4">Dauer</th>
              <th class="py-2 pr-4">Akteur</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in items" :key="d.id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40">
              <td class="py-2 pr-4 text-xs">
                <p class="font-mono">{{ new Date(d.ts).toLocaleString('de-DE') }}</p>
                <p class="text-slate-500"><Clock :size="10" class="inline" /> {{ relativeTime(d.ts) }}</p>
              </td>
              <td class="py-2 pr-4">
                <button class="font-medium text-sky-600 dark:text-sky-400 hover:underline" @click="router.push(`/apps/${d.app_id}`)">
                  {{ d.app_name }}
                </button>
              </td>
              <td class="py-2 pr-4 font-mono text-xs">
                <p class="flex items-center gap-1.5">
                  <Package :size="12" class="text-slate-400 flex-shrink-0" />
                  <span class="break-all">{{ d.image }}</span>
                </p>
                <p v-if="d.image_digest" class="text-slate-500 text-[10px] ml-4">{{ shortDigest(d.image_digest) }}</p>
              </td>
              <td class="py-2 pr-4 font-mono text-xs">
                <span v-if="d.git_sha" class="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                  <GitCommit :size="12" /> {{ d.git_sha.slice(0, 7) }}
                </span>
                <span v-else class="text-slate-400">—</span>
              </td>
              <td class="py-2 pr-4">
                <Badge :variant="sourceVariant(d.source) as any">{{ d.source }}</Badge>
              </td>
              <td class="py-2 pr-4">
                <Badge :variant="statusVariant(d.status) as any" dot>{{ d.status }}</Badge>
                <p v-if="d.notes" class="text-xs text-slate-500 mt-1 max-w-xs">{{ d.notes }}</p>
              </td>
              <td class="py-2 pr-4 text-xs text-slate-500 tabular-nums">
                {{ d.duration_s != null ? `${d.duration_s} s` : '—' }}
              </td>
              <td class="py-2 pr-4 text-xs">{{ d.actor }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <Card title="Lifecycle-Hook einrichten" subtitle="So melden Skripte einen Deployment-Eintrag">
      <div class="text-sm space-y-3">
        <p>
          Setze auf jedem Host die ENV-Variablen <code class="font-mono bg-slate-100 dark:bg-slate-800 px-1 rounded">COCKPIT_URL</code>
          und <code class="font-mono bg-slate-100 dark:bg-slate-800 px-1 rounded">LIFECYCLE_HOOK_TOKEN</code>. Der Token muss dem
          serverseitigen Wert (<code class="font-mono">LIFECYCLE_HOOK_TOKEN</code> im Cockpit-Container) entsprechen.
        </p>
        <p>Beispiel-Aufruf aus <code class="font-mono">lifecycle/start.sh</code>:</p>
        <pre class="text-xs font-mono bg-slate-100 dark:bg-slate-800 p-3 rounded overflow-x-auto"><code>/opt/cockpit/scripts/notify-deployment.sh \
    --app-id "{{ '$' }}APP_ID" \
    --image "ghcr.io/janpow77/auditworkshop-backend:{{ '$' }}IMAGE_TAG" \
    --git-sha "{{ '$' }}GIT_SHA" \
    --source lifecycle \
    --status ok \
    --duration-s "{{ '$' }}DURATION"</code></pre>
        <p class="text-xs text-slate-500">
          Der Hook ist best-effort: schlaegt er fehl, soll dein Lifecycle-Skript trotzdem als erfolgreich gelten.
        </p>
      </div>
    </Card>
  </div>
</template>
