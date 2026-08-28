<script setup lang="ts">
import type { WallHost } from '../../api/types'

defineProps<{ hosts: WallHost[]; statusKlasse: (wert: string | null | undefined) => string; statusText: (wert: string | null | undefined) => string; tage: (wert: number | null | undefined) => string; reihe: (key: string) => number[]; linie: (werte: number[]) => string; gb: (wert: number | null | undefined) => string }>()
</script>

<template>
  <div class="kachel hosts einblenden" style="--i: 4">
    <h4>Hosts</h4>
    <div v-for="h in hosts" :key="h.name" class="host-zeile">
      <div class="hz-kopf"><span><i :class="['punkt', statusKlasse(h.status)]" /><b>{{ h.name }}</b> <span class="mono dim">{{ h.ip }}</span></span><span class="mono">{{ h.stats.containers != null ? `${h.stats.containers} Container` : statusText(h.status) }}</span></div>
      <div class="hz-sub mono dim">{{ h.description || '—' }}{{ h.stats.uptime_s ? ` · Uptime ${tage(h.stats.uptime_s)}` : '' }}</div>
      <div v-if="h.stats.ok" class="balken-reihe">
        <span class="mono dim">Load</span><div class="balken"><i :style="{ width: `${Math.min(100, ((h.stats.load1 ?? 0) / (h.stats.cpus || 1)) * 100)}%` }" /></div>
        <span class="mono dim">RAM</span><div class="balken"><i :style="{ width: `${h.stats.mem_pct ?? 0}%` }" /></div>
        <span class="mono dim">Disk</span><div class="balken"><i :class="{ warn: (h.stats.disk_pct ?? 0) > 80 }" :style="{ width: `${h.stats.disk_pct ?? 0}%` }" /></div>
      </div>
      <svg v-if="reihe(`host.${h.name}.load1`).length > 1" class="host-verlauf" viewBox="0 0 100 30" preserveAspectRatio="none"><path :d="linie(reihe(`host.${h.name}.load1`))" class="verlauf" /></svg>
      <div v-if="h.stats.gpus?.length" class="balken-reihe gpu">
        <template v-for="(g, gi) in h.stats.gpus" :key="gi"><span class="mono dim">GPU{{ h.stats.gpus!.length > 1 ? gi + 1 : '' }}</span><div class="balken" :title="g.mem_total_mb ? `${gb(g.mem_used_mb)} / ${gb(g.mem_total_mb)} VRAM` : ''"><i class="gpu" :style="{ width: `${g.util_pct}%` }" /></div></template>
      </div>
    </div>
  </div>
</template>

<style scoped src="./hosts.css"></style>
