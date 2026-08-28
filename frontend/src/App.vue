<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import GlobalConfirmDialog from './components/shared/GlobalConfirmDialog.vue'
import Toasts from './components/shared/Toasts.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()

onMounted(() => {
  auth.hydrate()
})
</script>

<template>
  <RouterView />
  <GlobalConfirmDialog />
  <Toasts />
</template>
