<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus, Github, GitPullRequest, Trash2, RefreshCw, ExternalLink } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Modal from '../../components/shared/Modal.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { listRepos, addRepo, deleteRepo, repoBranches, repoPRs, repoRuns } from '../../api/github'
import { useToastStore } from '../../stores/toast'
import { useConfirmStore } from '../../stores/confirm'
import { extractError } from '../../api/client'
import { relativeTime } from '../../utils/format'
import type { Repo } from '../../api/types'

const toast = useToastStore()
const confirm = useConfirmStore()

const repos = ref<Repo[]>([])
const loading = ref(true)
const showModal = ref(false)
const form = ref({ owner: '', name: '', default_branch: 'main' })

const detail = ref<{ repo: Repo; branches: any[]; prs: any[]; runs: any[] } | null>(null)
const detailLoading = ref(false)

async function load() {
  loading.value = true
  try { repos.value = await listRepos() } catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}
onMounted(load)

async function add() {
  try {
    await addRepo(form.value)
    toast.success(`Repo ${form.value.owner}/${form.value.name} hinzugefuegt`)
    showModal.value = false
    form.value = { owner: '', name: '', default_branch: 'main' }
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function remove(r: Repo) {
  const ok = await confirm.ask({ title: `Repo entfernen?`, message: `${r.owner}/${r.name} aus Bookmark-Liste entfernen.`, danger: true })
  if (!ok) return
  try { await deleteRepo(r.id); toast.success('Entfernt'); await load() }
  catch (err) { toast.error(extractError(err)) }
}

async function loadDetail(r: Repo) {
  detail.value = null
  detailLoading.value = true
  try {
    const [b, p, ru] = await Promise.all([
      repoBranches(r.owner, r.name).catch(() => []),
      repoPRs(r.owner, r.name).catch(() => []),
      repoRuns(r.owner, r.name).catch(() => []),
    ])
    detail.value = { repo: r, branches: b, prs: p, runs: ru }
  } catch (err) { toast.error(extractError(err)) }
  finally { detailLoading.value = false }
}

function runStatusVariant(r: any): string {
  if (r.status === 'in_progress' || r.status === 'queued') return 'amber'
  if (r.conclusion === 'success') return 'green'
  if (r.conclusion === 'failure') return 'red'
  return 'slate'
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="GitHub-Repos" subtitle="Bookmark-Liste — Live-Daten via api.github.com">
      <template #actions>
        <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-sm font-semibold" @click="showModal = true">
          <Plus :size="14" /> Repo hinzufuegen
        </button>
      </template>

      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Repos...</div>
      <div v-else-if="!repos.length"><EmptyState title="Keine Repos" message="Lege Bookmarks fuer GitHub-Repos an." /></div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
              <th class="py-2 pr-4">Repo</th>
              <th class="py-2 pr-4">Default-Branch</th>
              <th class="py-2 pr-4">Letzte Sync</th>
              <th class="py-2 pr-2 text-right">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in repos" :key="r.id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40">
              <td class="py-2 pr-4">
                <div class="flex items-center gap-2">
                  <Github :size="14" class="text-slate-400" />
                  <button class="font-medium text-sky-600 dark:text-sky-400 hover:underline" @click="loadDetail(r)">{{ r.owner }}/{{ r.name }}</button>
                </div>
                <p class="text-[11px] text-slate-400">{{ r.description || '—' }}</p>
              </td>
              <td class="py-2 pr-4 font-mono text-xs">{{ r.default_branch }}</td>
              <td class="py-2 pr-4 text-xs text-slate-500">{{ relativeTime(r.last_sync_at) }}</td>
              <td class="py-2 pr-2">
                <div class="flex items-center justify-end gap-1">
                  <button class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Detail laden" @click="loadDetail(r)">
                    <RefreshCw :size="14" />
                  </button>
                  <a :href="`https://github.com/${r.owner}/${r.name}`" target="_blank" class="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Auf GitHub oeffnen">
                    <ExternalLink :size="14" />
                  </a>
                  <button class="rounded-md p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30" title="Entfernen" @click="remove(r)">
                    <Trash2 :size="14" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <Card v-if="detailLoading || detail" :title="detail ? `${detail.repo.owner}/${detail.repo.name}` : 'Lade Details...'">
      <div v-if="detailLoading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade GitHub-Details...</div>
      <div v-else-if="detail" class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div>
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Branches ({{ detail.branches.length }})</p>
          <ul class="space-y-1 text-xs font-mono">
            <li v-for="b in detail.branches.slice(0, 15)" :key="b.name" class="text-slate-700 dark:text-slate-300">
              {{ b.name }} <span class="text-slate-400">{{ b.sha }}</span>
            </li>
          </ul>
        </div>
        <div>
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5"><GitPullRequest :size="12" /> Pull Requests ({{ detail.prs.length }})</p>
          <ul v-if="detail.prs.length" class="space-y-2 text-xs">
            <li v-for="p in detail.prs" :key="p.number">
              <a :href="p.url" target="_blank" class="text-sky-600 hover:underline">#{{ p.number }} {{ p.title }}</a>
              <p class="text-slate-400 text-[10px]">{{ p.user }} · {{ relativeTime(p.updated_at) }}</p>
            </li>
          </ul>
          <p v-else class="text-xs text-slate-400">Keine offenen PRs</p>
        </div>
        <div>
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Letzte CI-Runs</p>
          <ul v-if="detail.runs.length" class="space-y-2 text-xs">
            <li v-for="r in detail.runs" :key="r.id" class="flex items-center justify-between gap-2">
              <div class="min-w-0">
                <a :href="r.url" target="_blank" class="font-medium text-slate-700 dark:text-slate-300 hover:underline truncate block">{{ r.name }}</a>
                <p class="text-[10px] text-slate-400">{{ r.branch }} · {{ relativeTime(r.updated_at) }}</p>
              </div>
              <Badge :variant="runStatusVariant(r) as any" dot>{{ r.conclusion || r.status }}</Badge>
            </li>
          </ul>
          <p v-else class="text-xs text-slate-400">Keine Runs</p>
        </div>
      </div>
    </Card>

    <Modal :open="showModal" title="Repo hinzufuegen" @close="showModal = false">
      <form class="space-y-3" @submit.prevent="add">
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Owner</span>
            <input v-model="form.owner" required placeholder="janriener" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Repo-Name</span>
            <input v-model="form.name" required placeholder="cockpit" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
          </label>
        </div>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Default-Branch</span>
          <input v-model="form.default_branch" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono" />
        </label>
      </form>
      <template #footer>
        <button class="rounded-md px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="showModal = false">Abbrechen</button>
        <button class="rounded-md px-3 py-1.5 text-sm font-semibold bg-sky-600 hover:bg-sky-700 text-white" @click="add">Hinzufuegen</button>
      </template>
    </Modal>
  </div>
</template>
