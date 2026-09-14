<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>入藏登记</h3>
      <label>期（出版登记）
        <select v-model="issueId">
          <option v-for="i in issues" :key="i.id" :value="i.id">{{ i.label }}</option>
        </select>
      </label>
      <label>条码
        <input v-model.trim="barcode" placeholder="扫描或输入唯一条码" />
      </label>
      <label>位置
        <select v-model="locationId">
          <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.code }} {{ l.name }}</option>
        </select>
      </label>
      <p class="tip">同一期可重复入藏：每次生成独立实体（复本号递增），并发入藏不会合并。</p>
      <p v-if="error" class="error">{{ error }}</p>
      <footer>
        <button @click="$emit('close')">取消</button>
        <button class="primary" :disabled="!issueId || !barcode || !locationId" @click="submit">入藏</button>
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

const issues = ref([])
const issueId = ref(null)
const barcode = ref('')
const locationId = ref(null)
const error = ref('')

onMounted(async () => {
  issues.value = await api.get(`/issues/?title=${props.titleId}`)
  if (issues.value.length) issueId.value = issues.value[issues.value.length - 1].id
  if (props.locations.length) locationId.value = props.locations[0].id
})

async function submit() {
  error.value = ''
  try {
    await api.post('/items/check_in/', {
      issue_id: issueId.value,
      barcode: barcode.value,
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
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 420px; max-width: 92vw; }
h3 { margin: 0 0 12px; font-size: 15px; }
label { display: block; font-size: 12px; color: #555; margin-bottom: 10px; }
select, input { display: block; width: 100%; margin-top: 3px; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.tip { font-size: 12px; color: #777; background: #f5f5f5; border-radius: 6px; padding: 6px 8px; }
.error { font-size: 12px; color: #c62828; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
button.primary { background: #1976d2; border-color: #1976d2; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
</style>
