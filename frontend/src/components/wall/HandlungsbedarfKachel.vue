<script setup lang="ts">
import type { Overview } from '../../api/types'

defineProps<{ alerts: Overview['alerts']; kritAnzahl: number; warnAnzahl: number }>()
</script>

<template>
  <div class="kachel alarm einblenden" :class="{ ruhig: !alerts.length, krit: kritAnzahl > 0 }" style="--i: 0">
    <h4>Handlungsbedarf <span class="dim">· {{ alerts.length ? `${kritAnzahl} kritisch · ${warnAnzahl} prüfen` : 'nichts offen' }}</span></h4>
    <div v-if="!alerts.length" class="ruhe"><i class="punkt ok" /><div><b>Alles läuft.</b><span class="mono dim">Hosts, Container, Sicherungen, Dienste und Zertifikate ohne Befund</span></div></div>
    <TransitionGroup v-else name="liste" tag="div" class="alarm-liste">
      <div v-for="a in alerts" :key="a.level + a.text" :class="['alarm-zeile', a.level]">
        <i :class="['punkt', a.level]" />
        <div class="a-text"><b>{{ a.text }}</b><span v-if="a.hint" class="mono dim">{{ a.hint }}</span></div>
        <a v-if="a.url" :href="a.url" target="_blank" rel="noopener" class="p-link mono">↗</a>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped src="./handlungsbedarf.css"></style>
