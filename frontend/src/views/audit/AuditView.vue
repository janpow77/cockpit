<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { History, Filter } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import ErrorState from '../../components/shared/ErrorState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { listAudit } from '../../api/audit'
import { useToastStore } from '../../stores/toast'
import { extractError } from '../../api/client'
import { formatDateTime, relativeTime } from '../../utils/format'
import type { AuditEntry } from '../../api/types'

const toast = useToastStore()
const entries = ref<AuditEntry[]>([])
const loading = ref(true)
const fehler = ref<string | null>(null)
const filter = ref({ action: '', target: '' })

async function load() {
  loading.value = true
  fehler.value = null
  try {
    entries.value = await listAudit({
      action: filter.value.action || undefined,
      target: filter.value.target || undefined,
      limit: 500,
    })
  } catch (err) { fehler.value = extractError(err); toast.error(fehler.value) }
  finally { loading.value = false }
}
onMounted(load)

function actionVariant(a: string): string {
  if (a.includes('delete')) return 'red'
  if (a.includes('create')) return 'green'
  if (a.includes('update')) return 'amber'
  if (a.includes('reveal')) return 'red'
  if (a.includes('restart') || a.includes('run')) return 'sky'
  return 'slate'
}

const grouped = computed(() => {
  const out: Record<string, AuditEntry[]> = {}
  for (const e of entries.value) {
    const day = e.ts.slice(0, 10)
    if (!out[day]) out[day] = []
    out[day].push(e)
  }
  return out
})
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Audit-Log" subtitle="Alle mutierenden Aktionen werden hier protokolliert">
      <template #actions>
        <input v-model="filter.action" placeholder="action filter..." class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1 text-xs font-mono" @keyup.enter="load" />
        <input v-model="filter.target" placeholder="target filter..." class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1 text-xs font-mono" @keyup.enter="load" />
        <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-xs font-semibold" @click="load">
          <Filter :size="12" /> Filtern
        </button>
      </template>

      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Audit...</div>
      <ErrorState v-else-if="fehler" title="Audit-Log konnte nicht geladen werden" :message="fehler" @retry="load()" />
      <div v-else-if="!entries.length"><EmptyState title="Keine Eintraege" /></div>
      <div v-else class="space-y-6">
        <div v-for="(group, day) in grouped" :key="day">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">{{ day }}</p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
                  <th class="py-1.5 pr-4">Zeit</th>
                  <th class="py-1.5 pr-4">Aktion</th>
                  <th class="py-1.5 pr-4">Target</th>
                  <th class="py-1.5 pr-4">Notes</th>
                  <th class="py-1.5 pr-4">IP</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in group" :key="e.id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40">
                  <td class="py-1.5 pr-4 text-xs tabular-nums" :title="formatDateTime(e.ts)">{{ relativeTime(e.ts) }}</td>
                  <td class="py-1.5 pr-4"><Badge :variant="actionVariant(e.action) as any" dot>{{ e.action }}</Badge></td>
                  <td class="py-1.5 pr-4 font-mono text-xs">{{ e.target || '—' }}</td>
                  <td class="py-1.5 pr-4 text-xs text-slate-500 truncate max-w-md">{{ e.notes || (e.after ? JSON.stringify(e.after).slice(0, 80) : '—') }}</td>
                  <td class="py-1.5 pr-4 font-mono text-xs text-slate-400">{{ e.ip || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Card>
  </div>
</template>
