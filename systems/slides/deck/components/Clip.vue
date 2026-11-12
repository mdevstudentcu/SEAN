<script setup lang="ts">
// A looping panel clip; in print and PDF export it shows its key still instead of frame 0.
import { computed } from 'vue'
import { useNav } from '@slidev/client'

const props = defineProps<{ src: string; poster: string; label: string }>()
const { isPrintMode } = useNav()
// Resolve against the deck's base, so the clips also play in the offline build opened from disk.
const at = (p: string) => (p.startsWith('/') ? import.meta.env.BASE_URL + p.slice(1) : p)
const src = computed(() => at(props.src))
const poster = computed(() => at(props.poster))
</script>

<template>
  <img v-if="isPrintMode" :src="poster" :alt="label" />
  <video v-else :src="src" :poster="poster" autoplay loop muted playsinline :aria-label="label" />
</template>
