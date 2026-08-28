import axios, { type AxiosError, type AxiosInstance } from 'axios'

const STORAGE_KEY = 'cockpit_admin_token'
const EXPIRY_KEY = 'cockpit_admin_token_exp'
const DEFAULT_TOKEN_LIFETIME_MS = 12 * 60 * 60 * 1000

export const TOKEN_KEY = STORAGE_KEY
export const TOKEN_EXP_KEY = EXPIRY_KEY
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'
export const API_BASE = import.meta.env.VITE_API_BASE || '/admin/api'

export const client: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      setToken(null)
      zurAnmeldung()
    }
    return Promise.reject(error)
  }
)

function zurAnmeldung(): void {
  if (typeof window !== 'undefined' && !window.location.pathname.endsWith('/login')) window.location.assign('/admin/login')
}

function gespeichertenWertLesen(key: string): string | null {
  try { return window.localStorage.getItem(key) }
  catch { return null }
}

function gespeichertenWertSetzen(key: string, value: string): void {
  try { window.localStorage.setItem(key, value) }
  catch { /* Speicherung kann im privaten Modus gesperrt sein. */ }
}

function gespeichertenWertLoeschen(key: string): void {
  try { window.localStorage.removeItem(key) }
  catch { /* Speicherung kann im privaten Modus gesperrt sein. */ }
}

function ablaufzeitLesen(tokenVorhanden: boolean): string | null {
  if (!tokenVorhanden) return null
  const gespeichert = gespeichertenWertLesen(EXPIRY_KEY)
  if (gespeichert && Number.isFinite(Date.parse(gespeichert))) return gespeichert
  const fallback = new Date(Date.now() + DEFAULT_TOKEN_LIFETIME_MS).toISOString()
  gespeichertenWertSetzen(EXPIRY_KEY, fallback)
  return fallback
}

export function setToken(token: string | null, expiresAt?: string | null): void {
  if (!token) {
    gespeichertenWertLoeschen(STORAGE_KEY)
    gespeichertenWertLoeschen(EXPIRY_KEY)
    return
  }
  const gueltigBis = expiresAt && Number.isFinite(Date.parse(expiresAt)) ? expiresAt : new Date(Date.now() + DEFAULT_TOKEN_LIFETIME_MS).toISOString()
  gespeichertenWertSetzen(STORAGE_KEY, token)
  gespeichertenWertSetzen(EXPIRY_KEY, gueltigBis)
}

export function getToken(): string | null {
  const token = gespeichertenWertLesen(STORAGE_KEY)
  if (!token) return null
  const expiresAt = ablaufzeitLesen(true)
  if (!expiresAt || Date.parse(expiresAt) <= Date.now()) {
    setToken(null)
    zurAnmeldung()
    return null
  }
  return token
}

export function getTokenExpiration(): string | null {
  const token = gespeichertenWertLesen(STORAGE_KEY)
  if (!token) return null
  const expiresAt = ablaufzeitLesen(true)
  if (!expiresAt || Date.parse(expiresAt) <= Date.now()) {
    setToken(null)
    zurAnmeldung()
    return null
  }
  return expiresAt
}

export function extractError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as any)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length) return detail[0].msg || JSON.stringify(detail[0])
    return err.message
  }
  if (err instanceof Error) return err.message
  return String(err)
}
