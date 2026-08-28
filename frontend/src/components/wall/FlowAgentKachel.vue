<script setup lang="ts">
import type { FlowAgentStand } from '../../api/types'

defineProps<{ flowAgent: FlowAgentStand; flowVersion: (wert: string | null) => string; flowStatusKlasse: (wert: string) => string; flowAlter: (wert: number | null) => string }>()
</script>

<template>
  <div class="kachel flow-agent einblenden" style="--i: 10">
    <h4><a v-if="flowAgent.url" :href="flowAgent.url" target="_blank" rel="noopener">flow-agent ↗</a><span v-else>flow-agent</span> <span class="dim">{{ flowAgent.ok ? `· Control Plane ok · ${flowVersion(flowAgent.version)} · ${flowAgent.hosts.length} Hosts` : `· ${flowAgent.note || 'nicht erreichbar'}` }}</span></h4>
    <div class="flow-hosts">
      <div v-for="h in flowAgent.hosts" :key="h.host" class="flow-hostzeile">
        <i :class="['punkt', flowStatusKlasse(h.status)]" />
        <div class="flow-name"><b>{{ h.host }}</b><span v-if="h.hostname && h.hostname !== h.host" class="mono dim">{{ h.hostname }}</span></div>
        <span class="flow-metrik mono">{{ h.projekte }} Projekte · {{ h.container }} Container · {{ h.gpu }} GPU</span>
        <div class="flow-chips"><span v-for="werkzeug in h.werkzeuge_fehlen.slice(0, 5)" :key="werkzeug" class="chip dim">{{ werkzeug }} fehlt</span><span v-if="h.tmux !== 'healthy'" class="chip dim">tmux: {{ h.tmux || '–' }}</span></div>
        <span class="flow-alter mono" :class="{ warn: h.alter_s != null && h.alter_s > 300 }">{{ flowAlter(h.alter_s) }}</span>
      </div>
    </div>
    <div class="flow-frische"><b>Frische:</b> {{ flowAgent.frische.healthy }} ok · {{ flowAgent.frische.degraded }} eingeschränkt · {{ flowAgent.frische.unhealthy }} kritisch</div>
    <div v-for="(befund, index) in flowAgent.frische.befunde.slice(0, 5)" :key="`${befund.host}-${befund.label}-${index}`" class="flow-befund" :class="{ ungesund: befund.status === 'unhealthy' }">⚠ {{ befund.label }} · {{ befund.host }} — {{ befund.detail }}</div>
    <div class="flow-aktionen mono" :class="{ offen: flowAgent.meldungen.pending_actions > 0 || flowAgent.meldungen.failed_actions_recent > 0 }"><template v-if="flowAgent.meldungen.pending_actions > 0 || flowAgent.meldungen.failed_actions_recent > 0">Aktionen: {{ flowAgent.meldungen.pending_actions }} {{ flowAgent.meldungen.pending_actions === 1 ? 'wartet' : 'warten' }} auf Freigabe · {{ flowAgent.meldungen.failed_actions_recent }} fehlgeschlagen</template><template v-else>Keine offenen Aktionen</template></div>
  </div>
</template>

<style scoped src="./flowAgent.css"></style>
