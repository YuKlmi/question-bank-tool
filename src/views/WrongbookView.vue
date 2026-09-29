<template>
  <div v-loading="loading">
    <div class="qtb-panel">
      <div class="qtb-panel-title">
        <span>错题本</span>
        <span class="qtb-muted">跨文档汇总，可只看某一份题库</span>
      </div>
      <div class="qtb-row">
        <el-select
          v-model="docId"
          placeholder="全部文档"
          clearable
          style="width: 260px"
          @change="load"
        >
          <el-option
            v-for="d in store.documents"
            :key="d.id"
            :label="d.name"
            :value="d.id"
          />
        </el-select>
        <el-button @click="load">刷新</el-button>
        <div class="qtb-spacer" />
        <span class="qtb-muted">共 {{ total }} 道错题</span>
      </div>
    </div>

    <el-row :gutter="14">
      <el-col :xs="24" :md="8">
        <div class="qtb-panel">
          <div class="qtb-panel-title">作答正确率</div>
          <EChart :option="chartOption" :height="220" />
        </div>
      </el-col>
      <el-col :xs="24" :md="16">
        <div class="qtb-panel">
          <div class="qtb-panel-title">错题分布</div>
          <EChart :option="docChartOption" :height="220" />
        </div>
      </el-col>
    </el-row>

    <div v-if="!items.length" class="qtb-panel">
      <div class="qtb-empty">还没有错题。做错的题会自动进入这里。</div>
    </div>

    <div v-for="it in items" :key="it.id" class="qtb-question-item">
      <div class="qtb-question-head" @click="toggle(it)">
        <el-icon>
          <component :is="expandedId === it.id ? 'ArrowDown' : 'ArrowRight'" />
        </el-icon>
        <strong>第 {{ it.display_no ?? it.seq + 1 }} 题</strong>
        <el-tag size="small" effect="plain">{{ typeLabel(it.type) }}</el-tag>
        <el-tag size="small" type="danger">错 {{ it.wrong_count }} 次</el-tag>
        <el-tag size="small" type="info" effect="plain">{{ it.doc_name }}</el-tag>
        <div class="qtb-spacer" />
        <span class="qtb-muted">{{ it.last_wrong_at ? it.last_wrong_at.replace('T', ' ').slice(0, 16) : '' }}</span>
      </div>
      <div v-if="expandedId === it.id" class="qtb-question-body">
        <div v-if="detail" >
          <div class="qtb-row" style="margin-bottom: 10px">
            <el-button size="small" @click="remove(it)">移出错题本</el-button>
            <el-button size="small" @click="goDoc(it)">到该文档做题</el-button>
            <el-button size="small" @click="toggleStar(it)">
              {{ detail.review.starred ? '取消收藏' : '收藏' }}
            </el-button>
          </div>
          <QuestionCard :question="detail" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import api from '../api';
import { useLibraryStore } from '../stores/library';
import { typeLabel } from '../utils/format';
import QuestionCard from '../components/QuestionCard.vue';
import EChart from '../components/EChart.vue';

const store = useLibraryStore();
const router = useRouter();

const loading = ref(false);
const docId = ref(null);
const items = ref([]);
const total = ref(0);
const expandedId = ref(null);
const detail = ref(null);
const stats = ref({ correct: 0, wrong: 0, accuracy: 0 });

const chartOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: true,
      label: { show: true, formatter: '{b}\n{c}' },
      data: [
        { value: stats.value.correct, name: '答对', itemStyle: { color: '#67c23a' } },
        { value: stats.value.wrong, name: '答错', itemStyle: { color: '#f56c6c' } },
      ],
    },
  ],
}));

const docChartOption = computed(() => {
  const counts = {};
  for (const it of items.value) {
    counts[it.doc_name] = (counts[it.doc_name] || 0) + 1;
  }
  const names = Object.keys(counts);
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 10, right: 20, top: 20, bottom: 10, containLabel: true },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: names.length ? names : ['（无）'] },
    series: [
      {
        type: 'bar',
        barWidth: 18,
        itemStyle: { color: '#f56c6c', borderRadius: [0, 4, 4, 0] },
        data: names.length ? names.map((n) => counts[n]) : [0],
      },
    ],
  };
});

async function load() {
  loading.value = true;
  try {
    const res = await api.listWrongbook(docId.value || null, 1, 200);
    items.value = res.items;
    total.value = res.total;
    stats.value = await api.docStats(docId.value || null);
    expandedId.value = null;
    detail.value = null;
  } catch (err) {
    ElMessage.error(`读取错题本失败：${err.message}`);
  } finally {
    loading.value = false;
  }
}

async function toggle(it) {
  if (expandedId.value === it.id) {
    expandedId.value = null;
    detail.value = null;
    return;
  }
  expandedId.value = it.id;
  detail.value = await api.getQuestion(it.id);
}

async function remove(it) {
  await api.setWrongbook(it.id, false);
  ElMessage.success('已移出错题本');
  await load();
}

async function toggleStar(it) {
  const r = await api.toggleStar(it.id);
  detail.value.review = r;
}

function goDoc(it) {
  router.push(`/doc/${it.doc_id}/practice`);
}

onMounted(async () => {
  if (!store.documents.length) await store.loadDocuments();
  await load();
});
</script>
