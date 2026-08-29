// Live-Daten-Polling fuer Dashboard, Hosts, Apps. Verwendet von den Views.
// Polling-Intervall: 30s. View-spezifischer Use:
//   const poll = usePollStore()
//   onMounted(() => poll.start('dashboard', loadDashboard, 30_000))
//   onBeforeUnmount(() => poll.stop('dashboard'))
import { defineStore } from 'pinia'
import { ref } from 'vue'

interface Job {
  timeoutId: number | null
  lastRun: number | null
  lastError: string | null
  inFlight: boolean
  generation: number
}

export const usePollStore = defineStore('poll', () => {
  const jobs = ref<Map<string, Job>>(new Map())
  const generationen = new Map<string, number>()

  function start(key: string, fn: () => Promise<void> | void, intervalMs: number) {
    stop(key)
    const generation = (generationen.get(key) ?? 0) + 1
    generationen.set(key, generation)
    const job: Job = { timeoutId: null, lastRun: null, lastError: null, inFlight: false, generation }
    jobs.value.set(key, job)

    const run = async () => {
      const aktuell = jobs.value.get(key)
      if (!aktuell || aktuell.generation !== generation || aktuell.inFlight) return
      aktuell.inFlight = true
      try {
        await fn()
        const nachLauf = jobs.value.get(key)
        if (!nachLauf || nachLauf.generation !== generation) return
        nachLauf.lastError = null
        nachLauf.lastRun = Date.now()
      } catch (err) {
        const nachLauf = jobs.value.get(key)
        if (!nachLauf || nachLauf.generation !== generation) return
        nachLauf.lastError = err instanceof Error ? err.message : String(err)
        nachLauf.lastRun = Date.now()
      } finally {
        const nachLauf = jobs.value.get(key)
        if (!nachLauf || nachLauf.generation !== generation) return
        nachLauf.inFlight = false
        nachLauf.timeoutId = window.setTimeout(() => { void run() }, intervalMs)
      }
    }
    void run()
  }

  function stop(key: string) {
    const j = jobs.value.get(key)
    generationen.set(key, (generationen.get(key) ?? j?.generation ?? 0) + 1)
    if (j?.timeoutId != null) window.clearTimeout(j.timeoutId)
    jobs.value.delete(key)
  }

  function stopAll() {
    for (const k of [...jobs.value.keys()]) stop(k)
  }

  return { jobs, start, stop, stopAll }
})
