<script setup lang="ts">
import type { Overview } from '../../api/types'

defineProps<{ backups: Overview['backups']; stundeMinute: (wert: string | null | undefined) => string; bytes: (wert: number) => string; relativ: (wert: string | null | undefined) => string }>()
</script>

<template>
  <div class="kachel einblenden" style="--i: 7">
    <h4>Sicherungen</h4>
    <div v-for="b in backups" :key="b.name" class="zeile"><span><i :class="['punkt', b.status]" /><b>{{ b.name }}</b></span><span class="mono">{{ stundeMinute(b.mtime) }} · {{ bytes(b.size_bytes) }} · {{ relativ(b.mtime) }}</span></div>
    <div v-if="!backups.length" class="dim">Kein Sicherungsverzeichnis eingebunden.</div>
  </div>
</template>

<style scoped src="./backups.css"></style>
