<script setup lang="ts">
import { GripVertical, Lightbulb } from 'lucide-vue-next'
import type { Auftrag } from '../../api/types'
import { MODUS_LABELS, PROFIL_LABELS, ZEIT_LABELS, agentChipLabel, dauer, dauerText, kosten, tokens } from './labels'

defineProps<{ auftrag: Auftrag; ausgewaehlt: boolean; jetzt: number }>()
defineEmits<{ oeffnen: []; dragstart: [event: DragEvent]; dragend: []; keydownVerschieben: [event: KeyboardEvent]; dragover: [event: DragEvent]; drop: [event: DragEvent] }>()
</script>

<template>
  <article class="auftrag" :class="[`status-${auftrag.status}`, { gezogen: ausgewaehlt }]" draggable="true" tabindex="0" @dragstart="$emit('dragstart', $event)" @dragend="$emit('dragend')" @dragover="$emit('dragover', $event)" @drop.stop="$emit('drop', $event)" @click="$emit('oeffnen')" @keydown="$emit('keydownVerschieben', $event)" @keydown.enter="$emit('oeffnen')">
    <div class="karten-titel"><GripVertical :size="15" class="griff" aria-hidden="true" /><h3>{{ auftrag.titel }}</h3><span v-if="auftrag.titel.startsWith('Vorschlag: ')" class="vorschlag-marke"><Lightbulb :size="10" /> Vorschlag</span><span v-if="auftrag.status === 'freigabe'" class="status-marke freigabe">Plan liegt vor</span><span v-else-if="auftrag.status === 'unterbrochen'" class="status-marke unterbrochen">Unterbrochen</span><span v-else-if="auftrag.status === 'fehler'" class="status-marke rot">Fehler</span><span v-else-if="auftrag.status === 'abgebrochen'" class="status-marke grau">Abgebrochen</span></div>
    <p class="projekt mono">{{ auftrag.projekt_name }} · {{ auftrag.host }}</p>
    <div class="chips"><span :class="['agent-chip', `agent-${auftrag.agent}`]" :title="auftrag.agent_auto && auftrag.agent_grund ? auftrag.agent_grund : undefined">{{ agentChipLabel(auftrag) }}</span><span class="modus-chip">{{ MODUS_LABELS[auftrag.modus] }}</span><span>{{ PROFIL_LABELS[auftrag.profil] }}</span><span>P{{ auftrag.prioritaet }}</span><span>{{ ZEIT_LABELS[auftrag.zeitfenster] }}</span></div>
    <p v-if="auftrag.status === 'unterbrochen' && auftrag.fehler" class="unterbrochen-fehler">{{ auftrag.fehler }}</p>
    <template v-if="auftrag.status === 'laeuft'"><div class="lauf"><i /><span>läuft</span><strong class="mono">{{ dauerText(dauer(auftrag, jetzt)) }}</strong></div><p v-if="auftrag.letzte_zeile" class="letzte mono" :title="auftrag.letzte_zeile">{{ auftrag.letzte_zeile }}</p></template>
    <template v-if="auftrag.status === 'fertig' || auftrag.status === 'fehler' || auftrag.status === 'abgebrochen'">
      <p v-if="auftrag.fehler" class="karten-fehler">{{ auftrag.fehler }}</p>
      <div v-if="auftrag.status === 'fertig'" class="qualitaet-chips"><span class="pruefung-badge" :class="auftrag.pruefung_ok === true ? 'ok' : auftrag.pruefung_ok === false ? 'krit' : 'ohne'">{{ auftrag.pruefung_ok === true ? 'Prüfung ✓' : auftrag.pruefung_ok === false ? 'Prüfung ✗' : 'ohne Prüfung' }}</span><a v-if="auftrag.pr_url" class="pr-chip" :href="auftrag.pr_url" target="_blank" rel="noopener" @click.stop>PR{{ auftrag.pr_checks ? ` · ${auftrag.pr_checks}` : '' }}</a></div>
      <div class="abschluss mono"><span>{{ dauerText(dauer(auftrag, jetzt)) }}</span><span>{{ kosten(auftrag.kosten_usd) }}</span><span>{{ tokens((auftrag.tokens_in ?? 0) + (auftrag.tokens_out ?? 0)) }} Tok.</span><a v-if="auftrag.diff_url" :href="auftrag.diff_url" target="_blank" rel="noopener" @click.stop>Diff ↗</a></div>
    </template>
  </article>
</template>

<style scoped src="./auftragKarte.css"></style>
