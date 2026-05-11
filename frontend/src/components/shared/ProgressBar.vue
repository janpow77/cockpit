<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ value: number; max?: number; variant?: 'sky' | 'green' | 'amber' | 'red' }>()

const pct = computed(() => {
  const max = props.max || 100
  return Math.min(100, Math.max(0, (props.value / max) * 100))
})

const color = computed(() => {
  switch (props.variant) {
    case 'green': return 'bg-green-500'
    case 'amber': return 'bg-amber-500'
    case 'red': return 'bg-red-500'
    default: return 'bg-sky-500'
  }
})
</script>

<template>
  <div class="h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
    <div class="h-full transition-all" :class="color" :style="{ width: pct + '%' }" />
  </div>
</template>
