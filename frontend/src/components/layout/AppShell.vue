<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { RouterView } from 'vue-router'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
import { usePollStore } from '../../stores/poll'

const poll = usePollStore()
const menueOffen = ref(false)

onBeforeUnmount(() => {
  // Schliesst alle Polling-Jobs beim AppShell-Unmount (z.B. Logout)
  poll.stopAll()
})
</script>

<template>
  <div class="flex min-h-screen" style="background: var(--app-bg)">
    <Sidebar :open="menueOffen" @close="menueOffen = false" />
    <div class="flex-1 flex flex-col min-w-0">
      <TopBar :menu-open="menueOffen" @toggle-menu="menueOffen = !menueOffen" />
      <main class="flex-1 px-6 py-6 overflow-x-hidden">
        <RouterView v-slot="{ Component }">
          <Transition mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>

<style scoped>
.v-enter-active, .v-leave-active { transition: opacity 0.15s ease; }
.v-enter-from, .v-leave-to { opacity: 0; }
</style>
