<script setup lang="ts">
// Minimal SVG-Sparkline ohne externe Library. Erwartet eine Liste numerischer
// Werte; zeichnet Polyline + optional Bereiche (z.B. Fehler in rot).
import { computed } from 'vue'

interface Props {
  values: number[]
  errorValues?: number[]
  height?: number
  width?: number
  strokeColor?: string
  errorColor?: string
  fillColor?: string | null
  showAxis?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  errorValues: () => [] as number[],
  height: 60,
  width: 280,
  strokeColor: '#0284c7',
  errorColor: '#dc2626',
  fillColor: null,
  showAxis: true,
})

const max = computed(() => {
  const all = [...props.values, ...props.errorValues]
  const v = Math.max(...all, 1)
  return v
})

const stepX = computed(() => {
  if (props.values.length <= 1) return props.width
  return props.width / (props.values.length - 1)
})

function toPath(arr: number[]): string {
  if (!arr.length) return ''
  const h = props.height
  const m = max.value
  return arr
    .map((v, i) => {
      const x = i * stepX.value
      const y = h - (v / m) * (h - 2) - 1
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
}

function toAreaPath(arr: number[]): string {
  if (!arr.length) return ''
  const path = toPath(arr)
  const lastX = (arr.length - 1) * stepX.value
  return `${path} L ${lastX.toFixed(1)} ${props.height} L 0 ${props.height} Z`
}
</script>

<template>
  <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" class="overflow-visible">
    <line
      v-if="showAxis"
      :x1="0" :y1="height - 1" :x2="width" :y2="height - 1"
      stroke="currentColor" stroke-opacity="0.15" stroke-width="1"
    />
    <path
      v-if="fillColor && values.length"
      :d="toAreaPath(values)"
      :fill="fillColor"
      fill-opacity="0.15"
    />
    <path
      v-if="values.length"
      :d="toPath(values)"
      fill="none"
      :stroke="strokeColor"
      stroke-width="1.5"
      stroke-linejoin="round"
      stroke-linecap="round"
    />
    <path
      v-if="errorValues.length"
      :d="toPath(errorValues)"
      fill="none"
      :stroke="errorColor"
      stroke-width="1.5"
      stroke-linejoin="round"
      stroke-linecap="round"
      stroke-dasharray="3,2"
    />
  </svg>
</template>
