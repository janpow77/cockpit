import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../src/stores/auth'
import { useConfirmStore } from '../src/stores/confirm'
import { useToastStore } from '../src/stores/toast'
import { useThemeStore } from '../src/stores/theme'
import { usePollStore } from '../src/stores/poll'

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})

describe('auth store', () => {
  it('starts unauthenticated', () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.token).toBe(null)
  })

  it('hydrate reads token from storage', () => {
    localStorage.setItem('cockpit_admin_token', 'tok-xyz')
    const auth = useAuthStore()
    auth.hydrate()
    expect(auth.token).toBe('tok-xyz')
    expect(auth.isAuthenticated).toBe(true)
  })
})

describe('confirm store', () => {
  it('ask returns true on confirm', async () => {
    const c = useConfirmStore()
    const p = c.ask({ title: 'x' })
    c.confirm()
    expect(await p).toBe(true)
  })
  it('ask returns false on cancel', async () => {
    const c = useConfirmStore()
    const p = c.ask({ title: 'x' })
    c.cancel()
    expect(await p).toBe(false)
  })
  it('ask sets pending and open', () => {
    const c = useConfirmStore()
    void c.ask({ title: 'Loeschen?', danger: true })
    expect(c.open).toBe(true)
    expect(c.pending?.title).toBe('Loeschen?')
    expect(c.pending?.danger).toBe(true)
  })
})

describe('toast store', () => {
  it('push adds and dismiss removes', () => {
    const t = useToastStore()
    const id = t.push('hello', 'success', 100_000)
    expect(t.toasts.length).toBe(1)
    t.dismiss(id)
    expect(t.toasts.length).toBe(0)
  })
  it('helpers set type', () => {
    const t = useToastStore()
    t.error('boom')
    expect(t.toasts[0].type).toBe('error')
  })
})

describe('theme store', () => {
  it('toggle flips between light and dark', () => {
    const th = useThemeStore()
    const before = th.theme
    th.toggle()
    expect(th.theme).not.toBe(before)
  })
})

describe('poll store', () => {
  it('start creates a job', async () => {
    const p = usePollStore()
    let calls = 0
    p.start('t1', () => { calls++ }, 9999_999)
    // Wait microtask
    await new Promise(r => setTimeout(r, 5))
    expect(calls).toBeGreaterThan(0)
    expect(p.jobs.has('t1')).toBe(true)
    p.stop('t1')
    expect(p.jobs.has('t1')).toBe(false)
  })

  it('stopAll clears jobs', () => {
    const p = usePollStore()
    p.start('a', () => {}, 9999_999)
    p.start('b', () => {}, 9999_999)
    p.stopAll()
    expect(p.jobs.size).toBe(0)
  })
})
