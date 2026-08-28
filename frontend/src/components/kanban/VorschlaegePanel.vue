<script setup lang="ts">
import type { AuftragAgent, Projekt } from '../../api/types'
import { VORSCHLAG_AGENTEN, graphifyDatum, projektKey, projektOption, quellenLabel, type ProjektGruppe } from './labels'

defineProps<{ form: { projektKey: string; agent: AuftragAgent }; projektGruppen: ProjektGruppe[]; projekt?: Projekt; busy: boolean }>()
defineEmits<{ submit: []; abbrechen: [] }>()
</script>

<template>
  <form class="formular vorschlaege-form" @submit.prevent="$emit('submit')">
    <p class="erklaerung">Der Agent liest Git-Verlauf, GitHub (Issues, PRs, CI), graphify-Analyse und Code und legt 5–10 priorisierte Vorschläge als Karten in den Eingang. Es wird nichts geändert.</p>
    <label>Projekt<select v-model="form.projektKey" required><optgroup v-for="gruppe in projektGruppen" :key="gruppe.host" :label="gruppe.host"><option v-for="eintrag in gruppe.liste" :key="projektKey(eintrag)" :value="projektKey(eintrag)" :disabled="!eintrag.ausfuehrbar">{{ projektOption(eintrag) }}</option></optgroup></select></label>
    <div v-if="projekt" class="projekt-details"><span :class="['quellen-chip', `quelle-${projekt.quelle}`]">{{ quellenLabel(projekt.quelle) }}</span><span v-for="technik in (projekt.technologien ?? []).slice(0, 4)" :key="technik" class="technik-chip">{{ technik }}</span><span class="graphify mono">graphify: {{ graphifyDatum(projekt.graphify_stand) }}</span></div>
    <p class="projekt-hinweis">Projektliste aus flow-agent (alle Hosts) und Werkstatt.</p>
    <fieldset class="agent-auswahl vorschlaege-agenten"><legend>Agent</legend><label v-for="agent in VORSCHLAG_AGENTEN" :key="agent.id" class="agent-radio" :class="{ aktiv: form.agent === agent.id }"><input v-model="form.agent" type="radio" name="vorschlaege-agent" :value="agent.id" /><span><strong>{{ agent.titel }}</strong><small>{{ agent.text }}</small></span></label></fieldset>
    <p v-if="form.agent === 'codex'" class="formular-hinweis codex-hinweis mono">Läuft auf dem NUC ohne Sandbox-Isolierung (bwrap nicht verfügbar) – Schutz durch eigenen Worktree und Branch.</p>
    <div class="aktionen"><button class="knopf" type="submit" :disabled="busy">Analyse starten</button><button class="knopf ghost" type="button" @click="$emit('abbrechen')">Abbrechen</button></div>
  </form>
</template>

<style scoped src="./vorschlaegePanel.css"></style>
