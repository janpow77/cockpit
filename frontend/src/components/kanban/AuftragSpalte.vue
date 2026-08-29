<script setup lang="ts">
import type { Auftrag } from '../../api/types'
import type { SpaltenStatus } from './labels'
import AuftragKarte from './AuftragKarte.vue'

defineProps<{ id: SpaltenStatus; titel: string; auftraege: Auftrag[]; dropZiel: boolean; gezogenId: string | null; jetzt: number }>()
defineEmits<{ dragover: [event: DragEvent]; dragleave: []; drop: [payload: { event: DragEvent; vorId?: string }]; oeffnen: [auftrag: Auftrag]; dragstart: [payload: { event: DragEvent; auftrag: Auftrag }]; dragend: []; keydownVerschieben: [payload: { event: KeyboardEvent; auftrag: Auftrag }]; neu: [] }>()
</script>

<template>
  <section class="spalte" :class="{ ziel: dropZiel }" @dragover="$emit('dragover', $event)" @dragleave.self="$emit('dragleave')" @drop="$emit('drop', { event: $event })">
    <header class="spalten-kopf"><h2>{{ titel }}</h2><span class="mono">{{ auftraege.length }}</span></header>
    <TransitionGroup name="karten" tag="div" class="karten" :css="false">
      <AuftragKarte v-for="auftrag in auftraege" :key="auftrag.id" :auftrag="auftrag" :ausgewaehlt="gezogenId === auftrag.id" :jetzt="jetzt" @dragstart="$emit('dragstart', { event: $event, auftrag })" @dragend="$emit('dragend')" @dragover="$emit('dragover', $event)" @drop="$emit('drop', { event: $event, vorId: auftrag.id })" @oeffnen="$emit('oeffnen', auftrag)" @keydown-verschieben="$emit('keydownVerschieben', { event: $event, auftrag })" />
    </TransitionGroup>
    <button v-if="!auftraege.length" class="leere-spalte" type="button" @click="id === 'eingang' ? $emit('neu') : undefined">{{ id === 'eingang' ? '+ Auftrag anlegen' : 'Keine Aufträge' }}</button>
  </section>
</template>

<style scoped src="./auftragSpalte.css"></style>
