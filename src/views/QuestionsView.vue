<template>
  <div v-loading="store.loadingQuestions">
    <div class="qtb-panel">
      <div class="qtb-row">
        <el-select
          v-model="groupSeq"
          placeholder="全部题组"
          clearable
          style="width: 220px"
          @change="(v) => store.setFilter({ groupSeq: v ?? null })"
        >
          <el-option
            v-for="g in store.groups"
            :key="g.seq"
            :label="`${g.title}（${g.questionCount}）`"
            :value="g.seq"
          />
        </el-select>

        <el-select
          v-model="reviewState"
          placeholder="全部状态"
          clearable
          style="width: 150px"
          @change="(v) => store.setFilter({ reviewState: v ?? null })"
        >
          <el-option label="待录入" value="pending_input" />
          <el-option label="待校对" value="pending" />
          <el-option label="已通过" value="ok" />
          <el-option label="已修正" value="fixed" />
        </el-select>

        <el-select
          v-model="type"
          placeholder="全部题型"
          clearable
          style="width: 130px"
          @change="(v) => store.setFilter({ type: v ?? null })"
        >
          <el-option
            v-for="(label, value) in TYPE_LABELS"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>

        <el-select
          v-model="hasAnswer"
          placeholder="不限答案"
          clearable
          style="width: 140px"
          @change="(v) => store.setFilter({ hasAnswer: v ?? null })"
        >
          <el-option label="已有答案" :value="true" />
          <el-option label="缺答案" :value="false" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="搜索题干关键词"
          clearable
          style="width: 220px"
          @keyup.enter="store.setFilter({ keyword })"
          @clear="store.setFilter({ keyword: '' })"
        >
          <template #append>
            <el-button @click="store.setFilter({ keyword })">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>

        <div class="qtb-spacer" />
        <el-button size="small" @click="resetFilters">重置</el-button>
        <span class="qtb-muted">共 {{ store.questionTotal }} 题</span>
      </div>
    </div>

    <div v-if="!store.questions.length" class="qtb-panel">
      <div class="qtb-empty">没有符合条件的题目</div>
    </div>

    <div
      v-for="item in store.questions"
      :key="item.id"
      class="qtb-question-item"
    >
      <div class="qtb-question-head" @click="toggle(item)">
        <el-icon>
          <component :is="expandedId === item.id ? 'ArrowDown' : 'ArrowRight'" />
        </el-icon>
        <strong>第 {{ item.display_no ?? item.seq + 1 }} 题</strong>
        <el-tag size="small" effect="plain">{{ typeLabel(item.type) }}</el-tag>
        <span class="qtb-flag" :class="`qtb-flag--${item.review_state}`">
          {{ reviewStateLabel(item.review_state) }}
        </span>
        <template v-if="item.group_title">
          <span class="qtb-muted">{{ item.group_title }}</span>
        </template>
        <div class="qtb-spacer" />
        <el-icon v-if="item.starred" color="#e6a23c"><StarFilled /></el-icon>
        <el-icon v-if="item.in_wrongbook" color="#f56c6c"><WarningFilled /></el-icon>
        <span class="qtb-muted">{{ item.option_count }} 选项</span>
        <span v-if="item.image_count" class="qtb-muted">· {{ item.image_count }} 图</span>
      </div>

      <!-- 题干预览：收起时也要能看见题目内容，否则整列看起来像"没有题目" -->
      <div
        v-if="expandedId !== item.id"
        class="qtb-question-preview"
        @click="toggle(item)"
      >
        {{ previewOf(item) }}
      </div>

      <div v-if="expandedId === item.id" class="qtb-question-body">
        <div v-if="loadingDetail" v-loading="true" style="height: 60px" />

        <template v-else-if="detail">
          <div class="qtb-row" style="margin-bottom: 12px">
            <el-button size="small" @click="editing = !editing">
              <el-icon style="margin-right: 4px"><Edit /></el-icon>
              {{ editing ? '取消编辑' : '编辑题目' }}
            </el-button>
            <el-button size="small" @click="toggleStar(detail)">
              <el-icon style="margin-right: 4px"><Star /></el-icon>
              {{ detail.review.starred ? '取消收藏' : '收藏' }}
            </el-button>
            <el-button size="small" @click="toggleWrong(detail)">
              {{ detail.review.in_wrongbook ? '移出错题本' : '加入错题本' }}
            </el-button>
            <div class="qtb-spacer" />
            <span class="qtb-muted">
              置信度 {{ confidenceText(detail.confidence) }}
              <template v-if="detail.answer_source">
                · 答案来源 {{ answerSourceLabel(detail.answer_source) }}
              </template>
            </span>
            <el-button size="small" text type="danger" @click="removeQuestion(detail)">
              删除题目
            </el-button>
          </div>

          <QuestionEditor
            v-if="editing"
            :question="detail"
            @saved="onSaved"
            @cancel="editing = false"
          />

          <QuestionCard :question="detail" editable />

          <AnnotationPanel
            :question-id="detail.id"
            :annotations="detail.annotations || []"
            @changed="reloadDetail"
          />
        </template>
      </div>
    </div>

    <div v-if="store.questionTotal > store.filters.pageSize" class="qtb-row" style="justify-content: center">
      <el-pagination
        layout="prev, pager, next, jumper"
        :total="store.questionTotal"
        :page-size="store.filters.pageSize"
        :current-page="store.filters.page"
        @current-change="(p) => store.setFilter({ page: p })"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api';
import { useLibraryStore } from '../stores/library';
import { TYPE_LABELS, answerSourceLabel, confidenceText, reviewStateLabel, typeLabel } from '../utils/format';
import QuestionCard from '../components/QuestionCard.vue';
import QuestionEditor from '../components/QuestionEditor.vue';
import AnnotationPanel from '../components/AnnotationPanel.vue';

const store = useLibraryStore();
const route = useRoute();

const expandedId = ref(null);
const loadingDetail = ref(false);
const detail = ref(null);
const editing = ref(false);

const groupSeq = ref(null);
const reviewState = ref(null);
const type = ref(null);
const hasAnswer = ref(null);
const keyword = ref('');

onMounted(async () => {
  await store.openDocument(Number(route.params.docId));
});

watch(
  () => route.params.docId,
  async (v) => {
    if (v) {
      collapsedAll();
      await store.openDocument(Number(v));
    }
  },
);

function collapsedAll() {
  expandedId.value = null;
  detail.value = null;
  editing.value = false;
}

/** 列表预览文案：图片题给明确提示，其余取题干前段 */
function previewOf(item) {
  const stem = String(item.stem || '').trim();
  if (!stem) {
    return item.stem_source === 'image' || item.image_count
      ? '〔题面为图片，点击展开查看原图并录入〕'
      : '〔题干为空，点击展开补录〕';
  }
  return stem.length > 110 ? `${stem.slice(0, 110)}…` : stem;
}

async function toggle(item) {
  if (expandedId.value === item.id) {
    collapsedAll();
    return;
  }
  expandedId.value = item.id;
  editing.value = false;
  await reloadDetail();
}

async function reloadDetail() {
  if (!expandedId.value) return;
  loadingDetail.value = true;
  try {
    detail.value = await api.getQuestion(expandedId.value);
    store.patchQuestion(detail.value.id, {
      starred: detail.value.review.starred,
      in_wrongbook: detail.value.review.in_wrongbook,
      review_state: detail.value.review_state,
      answer: detail.value.answer,
      stem: detail.value.stem,
      option_count: (detail.value.options || []).length,
    });
  } catch (err) {
    ElMessage.error(`读取题目失败：${err.message}`);
  } finally {
    loadingDetail.value = false;
  }
}

async function onSaved(updated) {
  editing.value = false;
  detail.value = updated;
  store.patchQuestion(updated.id, {
    review_state: updated.review_state,
    stem: updated.stem,
    answer: updated.answer,
    option_count: (updated.options || []).length,
  });
  await store.refreshCurrentDoc();
}

async function toggleStar(q) {
  const r = await api.toggleStar(q.id);
  detail.value.review = r;
  store.patchQuestion(q.id, { starred: r.starred });
}

async function toggleWrong(q) {
  const r = await api.setWrongbook(q.id, !q.review.in_wrongbook);
  detail.value.review = r;
  store.patchQuestion(q.id, { in_wrongbook: r.in_wrongbook });
  ElMessage.success(r.in_wrongbook ? '已加入错题本' : '已移出错题本');
}

async function removeQuestion(q) {
  await ElMessageBox.confirm(`删除第 ${q.display_no ?? q.seq + 1} 题？`, '确认', {
    type: 'warning',
  });
  await api.deleteQuestion(q.id);
  ElMessage.success('已删除');
  collapsedAll();
  await store.loadQuestions();
  await store.refreshCurrentDoc();
}

function resetFilters() {
  groupSeq.value = null;
  reviewState.value = null;
  type.value = null;
  hasAnswer.value = null;
  keyword.value = '';
  store.setFilter({
    groupSeq: null,
    reviewState: null,
    type: null,
    hasAnswer: null,
    keyword: '',
  });
}
</script>
