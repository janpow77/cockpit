<script setup lang="ts">
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'

defineProps<{ title?: string; message?: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-12 text-center text-amber-700 dark:text-amber-300">
    <div class="mb-3 rounded-full bg-amber-100 p-3 dark:bg-amber-900/30">
      <AlertTriangle :size="22" />
    </div>
    <p class="text-sm font-medium text-slate-800 dark:text-slate-200">{{ title || 'Daten konnten nicht geladen werden' }}</p>
    <p v-if="message" class="mt-1 max-w-sm text-xs text-slate-500 dark:text-slate-400">{{ message }}</p>
    <button class="mt-4 inline-flex items-center gap-1.5 rounded-md border border-amber-300 px-3 py-1.5 text-xs font-semibold hover:bg-amber-50 dark:border-amber-700 dark:hover:bg-amber-900/30" type="button" @click="$emit('retry')">
      <RefreshCw :size="13" /> Erneut versuchen
    </button>
  </div>
</template>
