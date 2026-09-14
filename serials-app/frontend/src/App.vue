<template>
  <div class="app">
    <header class="topbar">
      <h1>连续出版物登记系统</h1>
      <span class="sub">刊名沿革 · 卷期枚举 · 入藏 / 合订 / 拆订 / 移库</span>
    </header>

    <div class="body">
      <TitleList :titles="titles" :selected-id="selectedId" @select="selectTitle" />

      <main v-if="timeline" class="main">
        <div class="head-row">
          <div>
            <h2>{{ timeline.title.name }}</h2>
            <p class="meta">
              {{ timeline.title.frequency_display }} · 第{{ timeline.title.volume_start_number }}卷起
              · 每卷{{ timeline.title.months_per_volume }}个月
              <template v-if="timeline.title.status === 'CEASED'">
                · 已于 {{ timeline.title.ceased_year }}年{{ timeline.title.ceased_month }}月 停刊
              </template>
              <template v-if="timeline.title.predecessor_name">
                · 前身《{{ timeline.title.predecessor_name }}》
              </template>
            </p>
          </div>
          <div class="actions">
            <button @click="dialog = 'checkin'">入藏</button>
            <button @click="dialog = 'bind'">合订</button>
            <button @click="dialog = 'unbind'">拆订</button>
            <button @click="dialog = 'move'">移库</button>
            <button class="ghost" @click="refresh">刷新</button>
          </div>
        </div>

        <div class="stats">
          <span>应到 <b>{{ timeline.stats.expected }}</b></span>
          <span class="ok">在藏 <b>{{ timeline.stats.held }}</b></span>
          <span class="bad">缺藏 <b>{{ timeline.stats.missing }}</b></span>
          <span class="muted">缺号 <b>{{ timeline.stats.not_published }}</b></span>
        </div>

        <Timeline :data="timeline" @select="selectedSlot = $event" />
        <GapPanel :gaps="gaps" />
        <HistoryPanel :logs="logs" />
      </main>

      <main v-else class="main loading">加载中…</main>
    </div>

    <SlotDrawer v-if="selectedSlot" :slot="selectedSlot" @close="selectedSlot = null" />
    <CheckInDialog
      v-if="dialog === 'checkin'" :title-id="selectedId" :locations="locations"
      @close="dialog = null" @done="onActionDone"
    />
    <BindDialog
      v-if="dialog === 'bind'" :title-id="selectedId" :locations="locations"
      @close="dialog = null" @done="onActionDone"
    />
    <UnbindDialog
      v-if="dialog === 'unbind'" :title-id="selectedId"
      @close="dialog = null" @done="onActionDone"
    />
    <MoveDialog
      v-if="dialog === 'move'" :title-id="selectedId" :locations="locations"
      @close="dialog = null" @done="onActionDone"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from './api'
import TitleList from './components/TitleList.vue'
import Timeline from './components/Timeline.vue'
import SlotDrawer from './components/SlotDrawer.vue'
import GapPanel from './components/GapPanel.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import CheckInDialog from './components/CheckInDialog.vue'
import BindDialog from './components/BindDialog.vue'
import UnbindDialog from './components/UnbindDialog.vue'
import MoveDialog from './components/MoveDialog.vue'

const titles = ref([])
const locations = ref([])
const selectedId = ref(null)
const timeline = ref(null)
const gaps = ref([])
const logs = ref([])
const selectedSlot = ref(null)
const dialog = ref(null)

onMounted(async () => {
  ;[titles.value, locations.value] = await Promise.all([
    api.get('/titles/'),
    api.get('/locations/'),
  ])
  if (titles.value.length) selectTitle(titles.value[0].id)
})

async function selectTitle(id) {
  selectedId.value = id
  selectedSlot.value = null
  await refresh()
}

async function refresh() {
  if (!selectedId.value) return
  ;[timeline.value, gaps.value, logs.value] = await Promise.all([
    api.get(`/titles/${selectedId.value}/timeline/`),
    api.get(`/titles/${selectedId.value}/gaps/`),
    api.get(`/logs/?title=${selectedId.value}`),
  ])
  gaps.value = gaps.value.gaps || []
}

async function onActionDone() {
  dialog.value = null
  await refresh()
}
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif; background: #f4f6f8; color: #222; }
</style>

<style scoped>
.app { min-height: 100vh; display: flex; flex-direction: column; }
.topbar {
  background: #1a237e; color: #fff; padding: 10px 20px;
  display: flex; align-items: baseline; gap: 14px;
}
.topbar h1 { font-size: 17px; margin: 0; }
.topbar .sub { font-size: 12px; color: #9fa8da; }
.body { display: flex; gap: 14px; padding: 14px 20px; flex: 1; align-items: flex-start; }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.loading { color: #999; padding: 40px; }
.head-row { display: flex; justify-content: space-between; align-items: flex-end; gap: 10px; flex-wrap: wrap; }
.head-row h2 { margin: 0; font-size: 18px; }
.meta { margin: 4px 0 0; font-size: 12px; color: #777; }
.actions { display: flex; gap: 8px; }
.actions button {
  padding: 6px 14px; border: 1px solid #1976d2; border-radius: 6px;
  background: #1976d2; color: #fff; cursor: pointer; font-size: 13px;
}
.actions button.ghost { background: #fff; color: #1976d2; }
.actions button:hover { filter: brightness(1.08); }
.stats { display: flex; gap: 16px; font-size: 13px; color: #555; }
.stats .ok { color: #2e7d32; }
.stats .bad { color: #c62828; }
.stats .muted { color: #888; }
</style>
