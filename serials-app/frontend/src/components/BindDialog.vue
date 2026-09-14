<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>合订</h3>
      <p class="tip">选择本刊在架的册合订为一册合订本。合订后子期仍可检索到所在册。</p>
      <div class="items">
        <label v-for="it in items" :key="it.id" class="item-row">
          <input type="checkbox" :value="it.id" v-model="selected" />
          <span class="mono">{{ it.barcode }}</span>
          <span class="lbl">{{ it.issue_label }}</span>
          <span class="loc">{{ it.location.code }}</span>
        </label>
        <p v-if="!items.length" class="empty">本刊没有在架的册可合订。</p>
      </div>
      <label>合订本条码 <input v-model.trim="barcode" placeholder="唯一条码" /></label>
      <label>合订本题名 <input v-model.trim="label" placeholder="如：2025年1-6期合订本" /></label>
      <label>装订后位置
        <select v-model="locationId">
          <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.code }} {{ l.name }}</option>
        </select>
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <footer>
        <button @click="$emit('close')">取消</button>
        <button class="primary" :disabled="!selected.length || !barcode || !locationId" @click="submit">
          合订 {{ selected.length }} 册
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  titleId: { type: Number, required: true },
  locations: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'done'])

const items = ref([])
const selected = ref([])
const barcode = ref('')
const label = ref('')
const locationId = ref(null)
const error = ref('')

onMounted(async () => {
  items.value = await api.get(`/items/?title=${props.titleId}&status=ON_SHELF`)
  if (props.locations.length) locationId.value = props.locations[0].id
})

async function submit() {
  error.value = ''
  try {
    await api.post('/bound-volumes/bind/', {
      item_ids: selected.value,
      barcode: barcode.value,
      label: label.value,
      location_id: locationId.value,
      actor: 'librarian',
    })
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
.items { max-height: 220px; overflow-y: auto; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 10px; }
.item-row { display: flex; gap: 8px; align-items: center; padding: 5px 8px; font-size: 12px; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
.item-row:last-child { border-bottom: none; }
.mono { font-family: ui-monospace, monospace; }
.lbl { flex: 1; color: #444; }
.loc { color: #888; }
.empty { padding: 10px; font-size: 12px; color: #999; }
label { display: block; font-size: 12px; color: #555; margin-bottom: 8px; }
input, select { display: block; width: 100%; margin-top: 3px; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.item-row input { display: inline; width: auto; margin: 0; }
.error { font-size: 12px; color: #c62828; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
button.primary { background: #1976d2; border-color: #1976d2; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
</style>
