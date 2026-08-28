<script setup lang="ts">
import type { Overview } from '../../api/types'

defineProps<{ dienste: Overview['dienste']; diensteOk: number; tlsMin: number | null; zahl: (wert: number) => string; hoehe: (wert: number, reihe: number[]) => number }>()
</script>

<template>
  <div class="kachel dienste einblenden" style="--i: 1">
    <h4>Öffentliche Dienste <span class="dim">· {{ diensteOk }}/{{ dienste.length }} erreichbar{{ tlsMin != null ? ` · Zertifikate ≥ ${tlsMin} Tage` : '' }}</span></h4>
    <div v-for="d in dienste" :key="d.url" class="dienst">
      <i :class="['punkt', d.ok ? (d.ms != null && d.ms > 3000 ? 'warn' : 'ok') : 'krit']" />
      <a :href="d.url" target="_blank" rel="noopener" class="d-name" :title="d.note || d.url">{{ d.host }}</a>
      <span class="mono d-ms">{{ d.ms != null ? `${zahl(d.ms)} ms` : '–' }}</span>
      <span class="mono d-tls" :class="{ warn: d.tls_tage != null && d.tls_tage < 14 }" :title="d.tls_aussteller || ''">{{ d.tls_tage != null ? `TLS ${d.tls_tage} d` : (d.note || '') }}</span>
      <svg class="funken" viewBox="0 0 96 18" preserveAspectRatio="none" :title="d.requests_24h != null ? `${zahl(d.requests_24h)} Zugriffe in 24 h` : 'keine Verkehrsdaten'"><rect v-for="(v, i) in d.verlauf" :key="i" :x="i * 4" :y="18 - hoehe(v, d.verlauf)" width="3" :height="hoehe(v, d.verlauf)" :style="{ '--i': i }" /></svg>
      <span class="mono d-req">{{ d.requests_24h != null ? `${zahl(d.requests_24h)} / 24 h` : '' }}</span>
    </div>
    <div v-if="!dienste.length" class="dim">Keine öffentlichen Adressen hinterlegt.</div>
  </div>
</template>

<style scoped src="./dienste.css"></style>
