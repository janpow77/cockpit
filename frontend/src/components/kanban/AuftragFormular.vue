<script setup lang="ts">
import type { Projekt, Vorlage } from '../../api/types'
import { AGENTEN, MODI, PROFILE, graphifyDatum, projektKey, projektOption, quellenLabel, type AuftragFormModel, type ProjektGruppe } from './labels'

defineProps<{ variante: 'neu' | 'bearbeiten'; form: AuftragFormModel; busy: boolean; vorlagen?: Vorlage[]; projektGruppen?: ProjektGruppe[]; projekt?: Projekt }>()
defineEmits<{ submit: [planen: boolean]; vorlage: []; abbrechen: [] }>()
</script>

<template>
  <form class="formular" :class="{ 'edit-form': variante === 'bearbeiten' }" @submit.prevent="$emit('submit', false)">
    <template v-if="variante === 'neu'"><label>Vorlage<select v-model="form.vorlageId" @change="$emit('vorlage')"><option value="">– ohne Vorlage –</option><option v-for="vorlage in vorlagen" :key="vorlage.id" :value="vorlage.id">{{ vorlage.titel }}</option></select></label></template>
    <label>Titel<input v-model="form.titel" required :placeholder="variante === 'neu' ? 'Kurzer, eindeutiger Auftrag' : undefined" /></label>
    <template v-if="variante === 'neu'">
      <label>Projekt<select v-model="form.projektKey" required><optgroup v-for="gruppe in projektGruppen" :key="gruppe.host" :label="gruppe.host"><option v-for="eintrag in gruppe.liste" :key="projektKey(eintrag)" :value="projektKey(eintrag)" :disabled="!eintrag.ausfuehrbar">{{ projektOption(eintrag) }}</option></optgroup></select></label>
      <div v-if="projekt" class="projekt-details"><span :class="['quellen-chip', `quelle-${projekt.quelle}`]">{{ quellenLabel(projekt.quelle) }}</span><span v-for="technik in (projekt.technologien ?? []).slice(0, 4)" :key="technik" class="technik-chip">{{ technik }}</span><span class="graphify mono">graphify: {{ graphifyDatum(projekt.graphify_stand) }}</span></div>
      <p class="projekt-hinweis">Projektliste aus flow-agent (alle Hosts) und Werkstatt.</p>
    </template>
    <label>Auftragstext<textarea v-model="form.text" required rows="7" :placeholder="variante === 'neu' ? 'Behebe …, führe die Tests aus, committe mit sprechender Meldung' : undefined" /></label>
    <fieldset v-if="variante === 'neu'" class="agent-auswahl"><legend>Agent</legend><label v-for="agent in AGENTEN" :key="agent.id" class="agent-radio" :class="{ aktiv: form.agent === agent.id }"><input v-model="form.agent" type="radio" name="agent" :value="agent.id" /><span><strong>{{ agent.titel }}</strong><small>{{ agent.text }}</small></span></label></fieldset>
    <div v-else class="formular-zeile"><label>Agent<select v-model="form.agent"><option v-for="agent in AGENTEN" :key="agent.id" :value="agent.id">{{ agent.titel }}</option></select></label><label>Vorgehen<select v-model="form.modus"><option v-for="modus in MODI" :key="modus.id" :value="modus.id">{{ modus.titel }}</option></select></label></div>
    <p v-if="variante === 'neu' && form.agent === 'codex'" class="formular-hinweis codex-hinweis mono">Läuft auf dem NUC ohne Sandbox-Isolierung (bwrap nicht verfügbar) – Schutz durch eigenen Worktree und Branch.</p>
    <p v-if="variante === 'neu' && form.agent === 'gemini'" class="formular-hinweis mono">Gemini CLI muss auf dem Host angemeldet sein (API-Schlüssel in ~/.gemini/.env oder Antigravity-Login).</p>
    <fieldset v-if="variante === 'neu'" class="agent-auswahl modus-auswahl"><legend>Vorgehen</legend><label v-for="modus in MODI" :key="modus.id" class="agent-radio modus-radio" :class="{ aktiv: form.modus === modus.id }"><input v-model="form.modus" type="radio" name="modus" :value="modus.id" /><span><strong>{{ modus.titel }}</strong><small>{{ modus.text }}</small></span></label></fieldset>
    <p v-if="variante === 'neu'" class="formular-hinweis modus-hinweis">Das Profil gilt für die Umsetzung; Bericht und Plan laufen immer lesend.</p>
    <fieldset v-if="variante === 'neu' && form.modus !== 'bericht'"><legend>Profil</legend><label v-for="profil in PROFILE" :key="profil.id" class="radio"><input v-model="form.profil" type="radio" name="profil" :value="profil.id" /><span><strong>{{ profil.titel }}</strong><small>{{ profil.text }}</small></span></label></fieldset>
    <label v-else-if="variante === 'bearbeiten' && form.modus !== 'bericht'">Profil<select v-model="form.profil"><option v-for="profil in PROFILE" :key="profil.id" :value="profil.id">{{ profil.titel }}</option></select></label>
    <div :class="{ 'formular-zeile': variante === 'neu' }"><label>Priorität<select v-model.number="form.prioritaet"><option v-for="p in 5" :key="p" :value="p">P{{ p }}</option></select></label><label>Zeitfenster<select v-model="form.zeitfenster"><option value="sofort">sofort</option><option value="nachts">nachts</option><option value="nach_reset">nach Reset</option></select></label></div>
    <div class="aktionen"><button class="knopf" type="submit" :disabled="busy">{{ variante === 'neu' ? 'In Eingang legen' : 'Speichern' }}</button><button v-if="variante === 'neu'" class="knopf ghost" type="button" :disabled="busy" @click="$emit('submit', true)">Sofort planen</button><button v-else class="knopf ghost" type="button" @click="$emit('abbrechen')">Abbrechen</button></div>
  </form>
</template>

<style scoped src="./auftragFormular.css"></style>
