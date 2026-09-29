<template>
  <div v-loading="loading">
    <div class="qtb-panel">
      <div class="qtb-panel-title">
        <span>收藏与复习</span>
        <span class="qtb-muted">跨文档汇总；可打标签、按标签筛选复习</span>
      </div>
      <div class="qtb-row">
        <el-select
          v-model="docId"
          placeholder="全部文档"
          clearable
          style="width: 240px"
          @change="load"
        >
          <el-option v-for="d in store.documents" :key="d.id" :label="d.name" :value="d.id" />
        </el-select>
        <el-select
          v-model="tag"
          placeholder="全部标签"
          clearable
          style="width: 180px"
          @change="load"
        >
          <el-option v-for="t in tags" :key="t" :label="t" :value="t" />
        </el-select>
        <el-button @click="load">刷新</el-button>
        <div class="qtb-spacer" />
        <span class="qtb-muted">共 {{ total }} 道收藏</span>
      </div>
    </div>

    <div v-if="!items.length" class="qtb-panel">
      <div class="qtb-empty">
        还没有收藏的题目。在题目详情里点「收藏」即可加入这里。
      </div>
    </div>

    <div v-for="it in items" :key="it.id" class="qtb-question-item">
      <div class="qtb-question-head" @click="toggle(it)">
        <el-icon>
          <component :is="expandedId === it.id ? 'ArrowDown' : 'ArrowRight'" />
        </el-icon>
        <el-icon color="#e6a23c"><StarFilled /></el-icon>
        <strong>第 {{ it.display_no ?? it.seq + 1 }} 题</strong>
        <el-tag size="small" effect="plain">{{ typeLabel(it.type) }}</el-tag>
        <el-tag size="small" type="info" effect="plain">{{ it.doc_name }}</el-tag>
        <el-tag
          v-for="t in it.tags"
          :key="t"
          size="small"
          type="warning"
          effect="plain"
        >
          {{ t }}
        </el-tag>
        <div class="qtb-spacer" />
        <span v-if="it.wrong_count" class="qtb-muted">错 {{ it.wrong_count }} 次</span>
        <span v-if="it.correct_streak" class="qtb-muted">连对 {{ it.correct_streak }}</span>
      </div>

      <div v-if="expandedId === it.id" class="qtb-question-body">
        <div v-if="detail">
          <div class="qtb-row" style="margin-bottom: 10px">
            <el-button size="small" @click="unstar(it)">
              <el-icon style="margin-right: 4px"><Star /></el-icon>取消收藏
            </el-button>
            <el-select
              :model-value="detail.review.tags"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              placeholder="设置标签"
              style="width: 260px"
              @change="(v) => saveTags(it, v)"
            >
              <el-option v-for="t in tags" :key="t" :label="t" :value="t" />
            </el-select>
          </div>
          <QuestionCard :question="detail" />
          <AnnotationPanel
            :question-id="detail.id"
            :annotations="detail.annotations || []"
            @changed="reload"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import api from '../api';
import { useLibraryStore } from '../stores/library';
import { typeLabel } from '../utils/format';
import QuestionCard from '../components/QuestionCard.vue';
import AnnotationPanel from '../components/AnnotationPanel.vue';

const store = useLibraryStore();

const loading = ref(false);
const docId = ref(null);
const tag = ref(null);
const items = ref([]);
const tags = ref([]);
const total = ref(0);
const expandedId = ref(null);
const detail = ref(null);

async function load() {
  loading.value = true;
  try {
    const [res, tagList] = await Promise.all([
      api.listStarred(docId.value || null, 1, 200, tag.value || null),
      api.allTags(),
    ]);
    items.value = res.items;
    total.value = res.total;
    tags.value = tagList;
    expandedId.value = null;
    detail.value = null;
  } catch (err) {
    ElMessage.error(`读取收藏失败：${err.message}`);
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

async function reload() {
  if (expandedId.value) detail.value = await api.getQuestion(expandedId.value);
}

async function unstar(it) {
  await api.toggleStar(it.id);
  ElMessage.success('已取消收藏');
  await load();
}

async function saveTags(it, value) {
  await api.setTags(it.id, value);
  detail.value.review.tags = value;
  const idx = items.value.findIndex((x) => x.id === it.id);
  if (idx >= 0) items.value[idx].tags = value;
  tags.value = await api.allTags();
  ElMessage.success('标签已保存');
}

onMounted(async () => {
  if (!store.documents.length) await store.loadDocuments();
  await load();
});
</script>
