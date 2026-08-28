<script setup lang="ts">
import KiNutzungPanel from '../components/kanban/KiNutzungPanel.vue'
</script>

<template>
  <main class="ki-weiterleitung">
    <KiNutzungPanel :offen="true" />
  </main>
</template>

<style scoped>
.ki-weiterleitung {
  --grund: #0B1020; --flaeche: #131A2E; --flaeche-2: #1A2340; --linie: #263054;
  --text: #E7ECF7; --text-2: #AAB3CF; --text-3: #7F89AB; --akzent: #F2B84B;
  --ok: #4CC38A; --warn: #F2B84B; --krit: #F26D6D; --info: #6FA8FF;
  --display: 'Barlow Condensed', 'Arial Narrow', Arial, sans-serif;
  --body: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  --mono: 'IBM Plex Mono', SFMono-Regular, Consolas, monospace;
  min-height: 100vh; padding: 18px 26px; background: var(--grund); color: var(--text); font-family: var(--body);
}
</style>
