<script setup lang="ts">
// A media slot: shows public/media/<file> when it exists (image, or video for .mp4/.webm),
// otherwise a dashed placeholder that says what to capture and the file name to save it as.
import { computed, ref } from 'vue'

const props = defineProps<{ file: string; label: string; hint?: string; ratio?: string }>()
const src = computed(() => `/media/${props.file}`)
const isVideo = computed(() => /\.(mp4|webm|mov)$/i.test(props.file))
const missing = ref(false)
</script>

<template>
  <div class="media" :style="{ aspectRatio: ratio || '4 / 3' }">
    <template v-if="!missing">
      <video v-if="isVideo" :src="src" autoplay loop muted playsinline @error="missing = true" />
      <img v-else :src="src" :alt="label" @error="missing = true" />
    </template>
    <div v-else class="ph">
      <div class="ph-kind">{{ isVideo ? 'Video' : 'Photo' }} to add</div>
      <div class="ph-label">{{ label }}</div>
      <div v-if="hint" class="ph-hint">{{ hint }}</div>
      <code class="ph-file">public/media/{{ file }}</code>
    </div>
  </div>
</template>

<style scoped>
.media { position: relative; width: 100%; border-radius: 10px; overflow: hidden; background: var(--surface); }
.media img, .media video { width: 100%; height: 100%; object-fit: cover; display: block; }
.ph { position: absolute; inset: 0; border: 2px dashed var(--contour); border-radius: 10px; display: flex; flex-direction: column; justify-content: center; gap: 0.45rem; padding: 1rem 1.2rem; }
.ph-kind { font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--warn); }
.ph-label { font-family: var(--display); font-size: 0.85rem; letter-spacing: 0.04em; text-transform: uppercase; color: var(--fg); line-height: 1.3; }
.ph-hint { font-size: 0.85rem; color: var(--muted); line-height: 1.35; }
.ph-file { font-family: var(--mono); font-size: 0.75rem; color: var(--contour); background: none; padding: 0; }
</style>
