<script setup lang="ts">
import type { Overview } from '../../api/types'

defineProps<{ kira: NonNullable<Overview['kira']>; zahl: (wert: number) => string; kategorie: (wert: string | null) => string; relativ: (wert: string | null | undefined) => string }>()
</script>

<template>
  <div class="kachel kira einblenden" style="--i: 9">
    <h4>Kira · zuletzt gelernt <span class="dim">· {{ kira.total != null ? `${zahl(kira.total)} Einträge im Gedächtnis` : (kira.note || 'nicht erreichbar') }}{{ kira.host ? ` · ${kira.host}` : '' }}</span></h4>
    <TransitionGroup name="liste" tag="div">
      <div v-for="e in kira.entries.slice(0, 5)" :key="e.id || e.text" class="kira-zeile">
        <span class="chip kat">{{ kategorie(e.category) }}</span>
        <span class="k-text" :title="e.text">{{ e.text }}</span>
        <span class="mono dim">{{ e.project || '' }}{{ e.created_at ? ` · ${relativ(e.created_at)}` : '' }}</span>
      </div>
    </TransitionGroup>
    <div v-if="!kira.entries.length" class="dim">{{ kira.note || 'Noch keine Wissenseinträge.' }}</div>
  </div>
</template>

<style scoped src="./kira.css"></style>
