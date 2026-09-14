<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>拆订</h3>
      <p class="tip">拆订后每册恢复各自装订前的位置与状态（逐册恢复，不是只改一个条码）。</p>
      <div class="vols">
        <label v-for="bv in volumes" :key="bv.id" class="vol-row">
          <input type="radio" :value="bv.id" v-model="selectedId" />
          <span class="mono">{{ bv.barcode }}</span>
          <span class="lbl">{{ bv.label }}</span>
          <span class="loc">{{ bv.location.code }}</span>
          <span class="members">{{ bv.bound_items.length }} 册</span>
        </label>
        <p v-if="!volumes.length" class="empty">本刊没有在订的合订本。</p>
      </div>
      <div v-if="selected" class="preview">
        <strong>拆订后将恢复：</strong>
        <ul>
          <li v-for="bi in selected.bound_items" :key="bi.id">
            <span class="mono">{{ bi.item.barcode }}</span> → {{ bi.pre_location.code }}（{{ bi.pre_status === 'ON_SHELF' ? '在架' : bi.pre_status }}）
          </li>
        </ul>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <footer>
        <button @click="$emit('close')">取消</button>
        <button class="primary" :disabled="!selectedId" @click="submit">拆订</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  titleId: { type: Number, required: true },
})
const emit = defineEmits(['close', 'done'])

const volumes = ref([])
const selectedId = ref(null)
const error = ref('')

const selected = computed(() => volumes.value.find((v) => v.id === selectedId.value))

onMounted(async () => {
  volumes.value = await api.get(`/bound-volumes/?title=${props.titleId}&status=ACTIVE`)
})

async function submit() {
  error.value = ''
  try {
    await api.post(`/bound-volumes/${selectedId.value}/unbind/`, { actor: 'librarian' })
    emit('done')
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; align-items: center; justify-content: center; z-index: 40; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 520px; max-width: 94vw; }
h3 { margin: 0 0 8px; font-size: 15px; }
.tip { font-size: 12px; color: #777; background: #f5f5f5; border-radius: 6px; padding: 6px 8px; }
.vols { border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 10px; }
.vol-row { display: flex; gap: 8px; align-items: center; padding: 6px 8px; font-size: 12px; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
.vol-row:last-child { border-bottom: none; }
.vol-row input { width: auto; }
.mono { font-family: ui-monospace, monospace; }
.lbl { flex: 1; color: #444; }
.loc, .members { color: #888; }
.empty { padding: 10px; font-size: 12px; color: #999; }
.preview { font-size: 12px; background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; }
.preview ul { margin: 4px 0; padding-left: 18px; }
.error { font-size: 12px; color: #c62828; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
button.primary { background: #1976d2; border-color: #1976d2; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
</style>
