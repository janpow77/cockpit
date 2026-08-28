<script setup lang="ts">
import type { WallHost } from '../../api/types'

type Sitzung = NonNullable<WallHost['tmux']>[number] & { host: string }

defineProps<{ sitzungen: Sitzung[]; offenesFenster: string | null; fensterAusgabe: string; fensterLaden: boolean; paket: string; paketBestaetigen: boolean; paketBusy: boolean; seit: (wert: number | null) => string }>()
const emit = defineEmits<{ fensterOeffnen: [host: string, ziel: string]; ausgabeLaden: [host: string, ziel: string]; paketSenden: [host: string, ziel: string]; 'update:paket': [wert: string] }>()
</script>

<template>
  <div class="kachel sitzungen einblenden" style="--i: 3">
    <h4>Sitzungen <span class="dim">· tmux · {{ sitzungen.length }} {{ sitzungen.length === 1 ? 'Sitzung' : 'Sitzungen' }}</span></h4>
    <div v-for="t in sitzungen.slice(0, 10)" :key="t.host + '/' + t.name" class="sitzung">
      <div class="s-kopf"><i :class="['punkt', t.attached ? 'ok' : 'unbekannt']" /><b>{{ t.name }}</b><span class="mono dim">{{ t.host }} · {{ t.windows.length }} {{ t.windows.length === 1 ? 'Fenster' : 'Fenster' }}{{ t.created ? ` · seit ${seit(t.created)}` : '' }}{{ t.attached ? ' · verbunden' : '' }}</span></div>
      <div class="fenster mono">
        <button v-for="f in t.windows.slice(0, 12)" :key="f.index ?? f.name" :class="['chip', 'klick', { aktiv: f.active, offen: offenesFenster === `${t.host}|${t.name}:${f.index ?? f.name}` }]" :title="`Fenster ${f.name || '#' + (f.index ?? '')} öffnen: Ausgabe und Arbeitspaket`" @click="emit('fensterOeffnen', t.host, `${t.name}:${f.index ?? f.name}`)">{{ f.name || `#${f.index ?? ''}` }}<em v-if="f.cmd && f.cmd !== 'bash' && f.cmd !== 'zsh'"> · {{ f.cmd }}</em> ▸</button>
      </div>
      <template v-for="f in t.windows" :key="'p' + (f.index ?? f.name)">
        <div v-if="offenesFenster === `${t.host}|${t.name}:${f.index ?? f.name}`" class="terminal">
          <div class="t-kopf mono dim"><span>{{ t.host }} · {{ t.name }}:{{ f.name || '#' + (f.index ?? '') }}{{ f.cmd ? ` · ${f.cmd}` : '' }}</span><button class="knopf klein ghost" :disabled="fensterLaden" @click="emit('ausgabeLaden', t.host, `${t.name}:${f.index ?? f.name}`)">{{ fensterLaden ? 'lädt …' : 'Ausgabe neu laden' }}</button></div>
          <pre class="t-ausgabe mono">{{ fensterAusgabe || '(leer)' }}</pre>
          <form class="t-senden" @submit.prevent="emit('paketSenden', t.host, `${t.name}:${f.index ?? f.name}`)">
            <input :value="paket" class="t-eingabe mono" placeholder="Arbeitspaket – wird in diesem Fenster eingetippt und mit Enter abgeschickt …" maxlength="2000" @input="emit('update:paket', ($event.target as HTMLInputElement).value)" />
            <button type="submit" class="knopf klein" :class="{ warn: paketBestaetigen }" :disabled="paketBusy || !paket.trim()">{{ paketBusy ? 'sendet …' : paketBestaetigen ? 'Wirklich senden?' : 'Senden' }}</button>
          </form>
        </div>
      </template>
    </div>
    <div v-if="!sitzungen.length" class="dim">Keine tmux-Sitzungen sichtbar (Loopback-SSH des Self-Hosts nötig).</div>
  </div>
</template>

<style scoped src="./sitzungen.css"></style>
