<script setup lang="ts">
import type { Overview } from '../../api/types'

defineProps<{ github: Overview['github']; repos: Overview['github']['repos']; commitAnzahl: number | null; zahl: (wert: number | null) => string; relativ: (wert: string | null | undefined) => string }>()
</script>

<template>
  <div class="kachel github einblenden" style="--i: 11">
    <h4>GitHub <span class="dim">· {{ github.enabled ? `alle ${github.repos.length} Repositories · nach Aktivität · ${zahl(commitAnzahl)} Commits zuletzt` : 'kein Token' }}</span></h4>
    <div v-if="!github.enabled" class="dim">GITHUB_TOKEN setzen, dann erscheinen hier alle Repos mit Aktivität.</div>
    <div v-else-if="github.error" class="dim">{{ github.error }}</div>
    <div v-else class="repo-grid">
      <a v-for="r in repos" :key="r.full_name" :href="r.html_url" target="_blank" rel="noopener" class="repo" :class="{ still: !r.pushed_at || Date.now() - new Date(r.pushed_at).getTime() > 90 * 86400000 }" :title="r.description || r.full_name">
        <b>{{ r.name }}</b><span class="mono dim">{{ r.language || '—' }} · {{ relativ(r.pushed_at) }}{{ r.open_issues ? ` · ${r.open_issues} offen` : '' }}</span>
      </a>
    </div>
  </div>
</template>

<style scoped src="./github.css"></style>
