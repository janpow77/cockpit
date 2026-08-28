<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Settings as SettingsIcon, Save, Check, X, AlertTriangle } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Spinner from '../../components/shared/Spinner.vue'
import { getSettings, patchSettings } from '../../api/settings'
import { useToastStore } from '../../stores/toast'
import { extractError } from '../../api/client'
import { formatDuration } from '../../utils/format'
import type { Settings } from '../../api/types'
import WallSettingsCard from '../../components/settings/WallSettingsCard.vue'

const toast = useToastStore()
const settings = ref<Settings | null>(null)
const loading = ref(true)
const interval = ref<number>(60)

async function load() {
  loading.value = true
  try {
    settings.value = await getSettings()
    interval.value = settings.value.health_interval_s
  } catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}
onMounted(load)

async function save() {
  try {
    settings.value = await patchSettings({ health_interval_s: interval.value })
    toast.success('Einstellungen gespeichert')
  } catch (err) { toast.error(extractError(err)) }
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="Einstellungen" subtitle="System-Konfiguration">
      <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Einstellungen...</div>
      <div v-else-if="settings" class="space-y-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Status</p>
            <dl class="space-y-2 text-sm">
              <div class="flex justify-between border-b border-slate-100 dark:border-slate-800/60 py-1">
                <dt class="text-slate-500">Cockpit-Version</dt>
                <dd class="font-mono">{{ settings.cockpit_version }}</dd>
              </div>
              <div class="flex justify-between border-b border-slate-100 dark:border-slate-800/60 py-1">
                <dt class="text-slate-500">Uptime</dt>
                <dd>{{ formatDuration(settings.uptime_seconds * 1000) }}</dd>
              </div>
              <div class="flex justify-between border-b border-slate-100 dark:border-slate-800/60 py-1">
                <dt class="text-slate-500">Self-Host</dt>
                <dd class="font-mono">{{ settings.self_host_name }}</dd>
              </div>
              <div class="flex justify-between border-b border-slate-100 dark:border-slate-800/60 py-1">
                <dt class="text-slate-500">Data-Dir</dt>
                <dd class="font-mono">{{ settings.data_dir }}</dd>
              </div>
              <div class="flex justify-between border-b border-slate-100 dark:border-slate-800/60 py-1">
                <dt class="text-slate-500">Config-Pfad</dt>
                <dd class="font-mono text-xs">{{ settings.config_path }}</dd>
              </div>
            </dl>
          </div>

          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Integrationen</p>
            <div class="space-y-3">
              <div class="flex items-center justify-between p-3 rounded-md border border-slate-200 dark:border-slate-800">
                <div>
                  <p class="font-medium text-sm">Vault (COCKPIT_VAULT_KEY)</p>
                  <p class="text-xs text-slate-500">Fernet-Verschluesselung fuer Secrets</p>
                </div>
                <Badge :variant="settings.vault_enabled ? 'green' : 'red'" dot>
                  <Check v-if="settings.vault_enabled" :size="10" /><X v-else :size="10" />
                  {{ settings.vault_enabled ? 'aktiviert' : 'deaktiviert' }}
                </Badge>
              </div>
              <div class="flex items-center justify-between p-3 rounded-md border border-slate-200 dark:border-slate-800">
                <div>
                  <p class="font-medium text-sm">GitHub (GITHUB_TOKEN)</p>
                  <p class="text-xs text-slate-500">api.github.com Live-Abfragen</p>
                </div>
                <Badge :variant="settings.github_enabled ? 'green' : 'amber'" dot>
                  <Check v-if="settings.github_enabled" :size="10" /><X v-else :size="10" />
                  {{ settings.github_enabled ? 'aktiviert' : 'kein Token' }}
                </Badge>
              </div>
              <div v-if="settings.admin_password_is_default" class="flex items-start gap-2 p-3 rounded-md border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30">
                <AlertTriangle :size="16" class="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                <div class="text-xs text-amber-800 dark:text-amber-200">
                  <p class="font-semibold">Default-Passwort aktiv!</p>
                  <p class="mt-0.5">Setze die Env-Variable <code class="font-mono bg-amber-100 dark:bg-amber-800/40 px-1 rounded">COCKPIT_ADMIN_PASSWORD</code> und starte den Container neu.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div>
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Health-Loop</p>
          <div class="flex items-end gap-3">
            <label class="block">
              <span class="text-xs text-slate-500">Intervall (Sekunden)</span>
              <input v-model.number="interval" type="number" min="10" max="3600" class="mt-1 w-32 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm" />
            </label>
            <button class="inline-flex items-center gap-1.5 rounded-md bg-sky-600 hover:bg-sky-700 text-white px-3 py-2 text-sm font-semibold" @click="save">
              <Save :size="14" /> Speichern
            </button>
            <p class="text-xs text-slate-500 ml-2">Greift erst nach Container-Restart</p>
          </div>
        </div>
      </div>
    </Card>

    <WallSettingsCard />
  </div>
</template>
