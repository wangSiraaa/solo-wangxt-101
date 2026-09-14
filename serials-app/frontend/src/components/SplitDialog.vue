<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>合订册拆分</h3>
      <p class="tip">把部分成员移入新合订本，两侧均保留原有相对装订顺序。</p>
      <label>源合订本
        <select v-model="bvId" @change="selected = []">
          <option v-for="bv in volumes" :key="bv.id" :value="bv.id">
            {{ bv.barcode }} · {{ bv.label }}（{{ bv.bound_items.length }} 册）
          </option>
        </select>
      </label>
      <div v-if="current" class="items">
        <label v-for="bi in current.bound_items" :key="bi.id" class="item-row">
          <input type="checkbox" :value="bi.item.id" v-model="selected" />
          <span class="pos">册序{{ bi.position }}</span>
          <span class="mono">{{ bi.item.barcode }}</span>
          <span class="lbl">{{ bi.item.issue_label }}</span>
        </label>
      </div>
      <label>新合订本条码 <input v-model.trim="barcode" placeholder="唯一条码" /></label>
      <label>新合订本题名 <input v-model.trim="label" placeholder="如：2025年第3期（拆分）" /></label>
      <p v-if="error" class="error">{{ error }}</p>
      <footer>
        <button @click="$emit('close')">取消</button>
        <button class="primary" :disabled="!canSubmit" @click="submit">
          拆出 {{ selected.length }} 册
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  titleId: { type: Number, required: true },
  locations: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'done'])

const volumes = ref([])
const bvId = ref(null)
const selected = ref([])
const barcode = ref('')
const label = ref('')
const error = ref('')

const current = computed(() => volumes.value.find((v) => v.id === bvId.value))
const canSubmit = computed(
  () =>
    current.value &&
    selected.value.length > 0 &&
    selected.value.length < current.value.bound_items.length &&
    barcode.value,
)

onMounted(async () => {
  volumes.value = await api.get(`/bound-volumes/?title=${props.titleId}&status=ACTIVE`)
  if (volumes.value.length) bvId.value = volumes.value[0].id
})

async function submit() {
  error.value = ''
  try {
    await api.post(`/bound-volumes/${bvId.value}/split/`, {
      item_ids: selected.value,
      new_barcode: barcode.value,
      new_label: label.value,
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
label { display: block; font-size: 12px; color: #555; margin-bottom: 8px; }
select, input { display: block; width: 100%; margin-top: 3px; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.items { max-height: 200px; overflow-y: auto; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 10px; }
.item-row { display: flex; gap: 8px; align-items: center; padding: 5px 8px; font-size: 12px; border-bottom: 1px solid #f0f0f0; cursor: pointer; margin-bottom: 0; }
.item-row:last-child { border-bottom: none; }
.item-row input { display: inline; width: auto; margin: 0; }
.pos { color: #888; }
.mono { font-family: ui-monospace, monospace; }
.lbl { flex: 1; color: #444; }
.error { font-size: 12px; color: #c62828; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
button.primary { background: #1976d2; border-color: #1976d2; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
</style>
