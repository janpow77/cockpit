// Format-Helfer.

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return new Intl.NumberFormat('de-DE').format(n)
}

export function formatBytes(b: number | null | undefined): string {
  if (b === null || b === undefined) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`
  return `${(b / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch { return iso }
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  const diffS = Math.floor((Date.now() - t) / 1000)
  if (diffS < 5) return 'gerade eben'
  if (diffS < 60) return `vor ${diffS}s`
  if (diffS < 3600) return `vor ${Math.floor(diffS / 60)} min`
  if (diffS < 86400) return `vor ${Math.floor(diffS / 3600)} h`
  return `vor ${Math.floor(diffS / 86400)} d`
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  return `${Math.floor(ms / 60_000)} m ${Math.floor((ms % 60_000) / 1000)} s`
}

export function statusVariant(s: string | null | undefined): string {
  switch (s) {
    case 'online':
    case 'healthy':
    case 'ok':
      return 'green'
    case 'down':
    case 'failed':
    case 'offline':
      return 'red'
    case 'degraded':
    case 'unreachable':
    case 'ssh-down':
      return 'amber'
    case 'running':
      return 'blue'
    case 'never':
    case 'unknown':
    default:
      return 'slate'
  }
}
