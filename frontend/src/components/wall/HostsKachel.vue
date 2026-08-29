<script setup lang="ts">


import type { WallHost } from '../../api/types'

const props = defineProps<{ hosts: WallHost[]; statusKlasse: (wert: string | null | undefined) => string; statusText: (wert: string | null | undefined) => string; tage: (wert: number | null | undefined) => string; reihe: (key: string) => number[]; linie: (werte: number[]) => string; gb: (wert: number | null | undefined) => string }>()

// Auslastung: Load je Kern, sonst CPU-Prozent (flow-agent liefert kein load)
function auslastung(st: { load1?: number | null; cpus?: number | null; cpu_pct?: number | null }): number {
  if (st.load1 != null) return Math.min(100, ((st.load1 ?? 0) / (st.cpus || 1)) * 100)
  return Math.min(100, Math.max(0, st.cpu_pct ?? 0))
}

// Zeitreihe des Hosts: Load, sonst CPU-Prozent
function verlaufReihe(name: string): number[] {
  const l = props.reihe(`host.${name}.load1`)
  return l.length > 1 ? l : props.reihe(`host.${name}.cpu_pct`)
}
</script>

<template>
  <div class="kachel hosts einblenden" style="--i: 4">
    <h4>Hosts</h4>
    <div v-for="h in hosts" :key="h.name" class="host-zeile">
      <div class="hz-kopf"><span><i :class="['punkt', statusKlasse(h.status)]" /><b>{{ h.name }}</b> <span class="mono dim">{{ h.ip }}</span></span><span class="mono">{{ h.stats.containers != null ? `${h.stats.containers} Container` : statusText(h.status) }}</span></div>
      <div class="hz-sub mono dim">{{ h.description || '—' }}{{ h.stats.uptime_s ? ` · Uptime ${tage(h.stats.uptime_s)}` : '' }}</div>
      <div v-if="h.stats.ok" class="balken-reihe">
        <span class="mono dim">{{ h.stats.load1 != null ? 'Load' : 'CPU' }}</span><div class="balken"><i :style="{ width: `${auslastung(h.stats)}%` }" /></div>
        <span class="mono dim">RAM</span><div class="balken"><i :style="{ width: `${h.stats.mem_pct ?? 0}%` }" /></div>
        <span class="mono dim">Disk</span><div class="balken"><i :class="{ warn: (h.stats.disk_pct ?? 0) > 80 }" :style="{ width: `${h.stats.disk_pct ?? 0}%` }" /></div>
      </div>
      <svg v-if="verlaufReihe(h.name).length > 1" class="host-verlauf" viewBox="0 0 100 30" preserveAspectRatio="none"><path :d="linie(verlaufReihe(h.name))" class="verlauf" /></svg>
      <div v-if="h.stats.gpus?.length" class="balken-reihe gpu">
        <template v-for="(g, gi) in h.stats.gpus" :key="gi"><span class="mono dim">GPU{{ h.stats.gpus!.length > 1 ? gi + 1 : '' }}</span><div class="balken" :title="g.mem_total_mb ? `${gb(g.mem_used_mb)} / ${gb(g.mem_total_mb)} VRAM` : ''"><i class="gpu" :style="{ width: `${g.util_pct}%` }" /></div></template>
      </div>
    </div>
  </div>
</template>

<style scoped src="./hosts.css"></style>
