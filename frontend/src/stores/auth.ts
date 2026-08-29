import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '../api/auth'
import { setToken, getToken, getTokenExpiration, extractError } from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getToken())
  const expiresAt = ref<string | null>(getTokenExpiration())
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  function hydrate() {
    token.value = getToken()
    expiresAt.value = token.value ? getTokenExpiration() : null
  }

  async function login(username: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const result = await authApi.login(username, password)
      token.value = result.token
      setToken(result.token, result.expires_at)
      expiresAt.value = getTokenExpiration()
      return true
    } catch (err) {
      error.value = extractError(err)
      return false
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try { await authApi.logout() } catch { /* ignore */ }
    token.value = null
    expiresAt.value = null
    setToken(null)
  }

  return { token, expiresAt, loading, error, isAuthenticated, login, logout, hydrate }
})
