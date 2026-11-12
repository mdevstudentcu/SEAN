<script setup lang="ts">
// A looping panel clip; in print and PDF export it shows its key still instead of frame 0.
import { useNav } from '@slidev/client'

defineProps<{ src: string; poster: string; label: string }>()
const { isPrintMode } = useNav()
</script>

<template>
  <img v-if="isPrintMode" :src="poster" :alt="label" />
  <video v-else :src="src" :poster="poster" autoplay loop muted playsinline :aria-label="label" />
</template>
