<script setup lang="ts">
import type { Overview } from '../../api/types'

type Repo = Overview['werkstatt'][number]['repos'][number] & { host: string }

defineProps<{ repos: Repo[]; summe: string; naechsterSchritt: Repo | null; aeltere: number; alle: boolean; repoUrl: (name: string) => string | null; relativ: (wert: string | null) => string }>()
defineEmits<{ umschalten: [] }>()
</script>

<template>
  <div class="kachel werkstatt einblenden" style="--i: 2">
    <h4>Werkstatt <span class="dim">· {{ summe }}</span></h4>
    <div v-if="naechsterSchritt" class="weiter"><span class="chip pause">⏸ {{ naechsterSchritt.name }}</span><b>Nächster Schritt:</b> {{ naechsterSchritt.next_step }}</div>
    <TransitionGroup name="liste" tag="div">
      <div v-for="r in repos" :key="r.host + '/' + r.name" class="repo-zeile">
        <div class="r-kopf">
          <a v-if="repoUrl(r.name)" :href="repoUrl(r.name)!" target="_blank" rel="noopener" class="r-name" title="Repository auf GitHub öffnen">{{ r.name }} ↗</a>
          <b v-else>{{ r.name }}</b><span class="mono dim">{{ r.host }} · {{ r.branch }}</span>
          <span v-if="r.pause" class="chip pause" :title="`Pause seit ${relativ(r.pause)}`">⏸ Pause</span>
          <span v-else-if="r.dirty" class="chip dirty">{{ r.dirty }} ungesichert</span>
          <span v-else-if="r.ahead" class="chip ahead">{{ r.ahead }} nicht gepusht</span>
        </div>
        <div class="mono dim r-sub" :title="r.next_step || r.message">{{ r.next_step ? `→ ${r.next_step}` : (r.message || '—') }} · {{ relativ(r.pause || r.last_commit) }}</div>
      </div>
    </TransitionGroup>
    <div v-if="!repos.length" class="dim">Kein Projektverzeichnis erreichbar.</div>
    <button v-if="aeltere" class="knopf klein ghost schalter" @click="$emit('umschalten')">{{ alle ? 'nur aktive zeigen' : `+ ${aeltere} ältere zeigen` }}</button>
  </div>
</template>

<style scoped src="./werkstatt.css"></style>
