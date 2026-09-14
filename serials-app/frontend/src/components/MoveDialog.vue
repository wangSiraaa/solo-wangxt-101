<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>移库</h3>
      <label>对象类型
        <select v-model="kind">
          <option value="item">册（在架）</option>
          <option value="volume">合订本（在订）</option>
        </select>
      </label>
      <label v-if="kind === 'item'">选择册
        <select v-model="itemId">
          <option v-for="it in items" :key="it.id" :value="it.id">
            {{ it.barcode }} · {{ it.issue_label }}（现 {{ it.location.code }}）
          </option>
        </select>
      </label>
      <label v-else>选择合订本
        <select v-model="volumeId">
          <option v-for="bv in volumes" :key="bv.id" :value="bv.id">
            {{ bv.barcode }} · {{ bv.label }}（现 {{ bv.location.code }}）
          </option>
        </select>
      </label>
      <p v-if="kind === 'item'" class="tip">已装订的册须随合订本整体移库。</p>
      <label>目标位置
        <select v-model="locationId">
          <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.code }} {{ l.name }}</option>
        </select>
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <footer>
        <button @click="$emit('close')">取消</button>
        <button class="primary" :disabled="!targetId || !locationId" @click="submit">移库</button>
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

const kind = ref('item')
const items = ref([])
const volumes = ref([])
const itemId = ref(null)
const volumeId = ref(null)
const locationId = ref(null)
const error = ref('')

const targetId = computed(() => (kind.value === 'item' ? itemId.value : volumeId.value))

onMounted(async () => {
  ;[items.value, volumes.value] = await Promise.all([
    api.get(`/items/?title=${props.titleId}&status=ON_SHELF`),
    api.get(`/bound-volumes/?title=${props.titleId}&status=ACTIVE`),
  ])
  if (items.value.length) itemId.value = items.value[0].id
  if (volumes.value.length) volumeId.value = volumes.value[0].id
  if (props.locations.length) locationId.value = props.locations[0].id
})

async function submit() {
  error.value = ''
  try {
    const path =
      kind.value === 'item'
        ? `/items/${itemId.value}/move/`
        : `/bound-volumes/${volumeId.value}/move/`
    await api.post(path, { location_id: locationId.value, actor: 'librarian' })
    emit('done')
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; align-items: center; justify-content: center; z-index: 40; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 460px; max-width: 92vw; }
h3 { margin: 0 0 12px; font-size: 15px; }
label { display: block; font-size: 12px; color: #555; margin-bottom: 10px; }
select { display: block; width: 100%; margin-top: 3px; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; }
.tip { font-size: 12px; color: #777; background: #f5f5f5; border-radius: 6px; padding: 6px 8px; }
.error { font-size: 12px; color: #c62828; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
button.primary { background: #1976d2; border-color: #1976d2; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
</style>
