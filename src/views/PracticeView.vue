<template>
  <div>
    <div class="qtb-panel">
      <div class="qtb-panel-title">练习设置</div>
      <div class="qtb-row">
        <el-select v-model="mode" style="width: 200px">
          <el-option
            v-for="m in PRACTICE_MODES"
            :key="m.value"
            :label="m.label"
            :value="m.value"
          />
        </el-select>
        <el-input-number v-model="limit" :min="1" :max="maxLimit" />
        <span v-if="docQuestionCount" class="qtb-muted">共 {{ docQuestionCount }} 题</span>
        <el-tag v-if="restored" size="small" type="success" effect="plain">
          已恢复上次进度
        </el-tag>
        <el-button type="primary" :loading="loading" @click="start">
          {{ questions.length ? '重新抽题' : '开始练习' }}
        </el-button>
        <div class="qtb-spacer" />
        <span v-if="questions.length" class="qtb-muted">
          第 {{ index + 1 }} / {{ questions.length }} 题
        </span>
      </div>
    </div>

    <div v-if="!questions.length" class="qtb-panel">
      <div class="qtb-empty">
        <p>选择练习方式后点击「开始练习」。</p>
        <p class="qtb-muted">练习范围默认限定在当前文档内。</p>
      </div>
    </div>

    <template v-else>
      <div class="qtb-panel">
        <div class="qtb-row" style="margin-bottom: 12px">
          <el-button size="small" :disabled="index === 0" @click="go(index - 1)">
            <el-icon style="margin-right: 4px"><ArrowLeft /></el-icon>上一题
          </el-button>
          <el-button size="small" :disabled="index >= questions.length - 1" @click="go(index + 1)">
            下一题<el-icon style="margin-left: 4px"><ArrowRight /></el-icon>
          </el-button>
          <div class="qtb-spacer" />
          <el-tag size="small" effect="plain">{{ typeLabel(current.type) }}</el-tag>
          <el-tag v-if="current.display_no" size="small" type="info" effect="plain">
            原题号 {{ current.display_no }}
          </el-tag>
        </div>

        <el-progress
          :percentage="Math.round(((index + 1) / questions.length) * 100)"
          :show-text="false"
          style="margin-bottom: 14px"
        />

        <!-- 判断题：用对/错两键作答 -->
        <QuestionCard
          v-if="current.type === 'judge'"
          :question="current"
          :selected="state.selected"
          :show-answer="showAnswer"
          :correct="state.correct"
        />
        <div v-if="current.type === 'judge' && !state.submitted" class="qtb-row" style="margin-top: 12px">
          <el-button type="success" size="large" @click="selectJudge('对')">对</el-button>
          <el-button type="danger" size="large" @click="selectJudge('错')">错</el-button>
        </div>

        <!-- 填空题：多空用 / 分隔 -->
        <template v-else-if="current.type === 'blank'">
          <QuestionCard
            :question="current"
            :selected="state.selected"
            :show-answer="showAnswer"
            :correct="state.correct"
          />
          <el-input
            v-model="state.blankInput"
            :disabled="state.submitted"
            placeholder="多个空用 / 分隔，例如：北京/上海"
            style="margin-top: 12px"
          />
        </template>

        <!-- 选择题 -->
        <QuestionCard
          v-else
          :question="current"
          :selected="state.selected"
          :show-answer="showAnswer"
          :interactive="!state.submitted"
          :correct="state.correct"
          @select="onSelect"
        />

        <!-- 主观题：不自动判分 -->
        <div v-if="current.grade_mode === 'self'" style="margin-top: 12px">
          <el-input
            v-model="state.essayInput"
            :disabled="state.submitted"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="写下你的作答（不自动判分，提交后对照参考答案自评）"
          />
        </div>

        <div class="qtb-row" style="margin-top: 16px; align-items: center">
          <el-result
            v-if="state.submitted && state.correct !== null"
            :icon="state.correct ? 'success' : 'error'"
            :title="state.correct ? '答对了' : '答错了'"
            style="padding: 0; margin-right: 12px"
          />
          <el-button
            v-if="!state.submitted"
            type="primary"
            :disabled="!canSubmit"
            @click="submit"
          >
            提交并对照答案
          </el-button>
          <template v-if="state.submitted && current.grade_mode === 'self'">
            <span>自评：</span>
            <el-button
              v-for="level in ['掌握', '模糊', '不会']"
              :key="level"
              size="small"
              :type="state.assessLevel === level ? 'primary' : 'default'"
              @click="assess(level)"
            >
              {{ level }}
            </el-button>
          </template>
          <el-button v-if="state.submitted && !state.revealed" @click="reveal">
            查看解析
          </el-button>
          <div class="qtb-spacer" />
          <span class="qtb-muted">已作答 {{ answeredCount }} / {{ questions.length }}</span>
        </div>
      </div>

      <!-- 答题卡：直接跳题，不必逐题翻 -->
      <div class="qtb-panel">
        <div class="qtb-panel-title">
          <span>答题卡</span>
          <span class="qtb-muted">点序号可直接跳题</span>
        </div>
        <div class="qtb-row" style="gap: 6px">
          <el-button
            v-for="(q, i) in questions"
            :key="q.id"
            size="small"
            :type="i === index ? 'primary' : (cards[q.id] && cards[q.id].submitted ? 'success' : 'default')"
            :plain="i !== index"
            style="min-width: 40px"
            @click="go(i)"
          >
            {{ q.display_no ?? i + 1 }}
          </el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import api from '../api';
import { useLibraryStore } from '../stores/library';
import { PRACTICE_MODES, typeLabel } from '../utils/format';
import QuestionCard from '../components/QuestionCard.vue';

const store = useLibraryStore();
const route = useRoute();
const router = useRouter();

const mode = ref('sequence');
/** 抽题量：文档加载后会被拉满为该文档已识别的题目总数，20 只是无文档时的兜底 */
const limit = ref(20);
const loading = ref(false);
const questions = ref([]);
const index = ref(0);
/** 每题独立的作答状态：切换题目不会丢掉已选答案 */
const cards = reactive({});
let startedAt = Date.now();
/** 本次进入是否恢复了上次进度 */
const restored = ref(false);
let saveTimer = null;
/** 恢复进度期间挂起保存：否则中途的空草稿会把已存的作答覆盖掉 */
let suspended = false;

const current = computed(() => questions.value[index.value] || {});
const state = computed(() => cards[current.value.id] || blankState());

/** 当前文档已识别的题目总数 */
const docQuestionCount = computed(() => Number(store.currentDoc?.question_count) || 0);
/** 抽题上限跟着总数走，否则大文档会被输入框的 max 卡住 */
const maxLimit = computed(() => Math.max(1, docQuestionCount.value));

/**
 * 默认抽题量 = 该文档已识别的全部题目。
 * 放在文档加载之后调用：题目总数来自 currentDoc，加载前拿不到。
 */
function applyDefaultLimit() {
  if (docQuestionCount.value > 0) limit.value = docQuestionCount.value;
}

const answeredCount = computed(
  () => Object.values(cards).filter((c) => c.submitted).length,
);

/**
 * 答案与解析的展示开关。
 * 提交只给出「答对/答错」，答案、解析、正确选项标记都要再点
 * 「查看解析」才展开——默认直接亮出来就失去了练习的意义。
 */
const showAnswer = computed(() => state.value.submitted && state.value.revealed);

const canSubmit = computed(() => {
  if (!current.value.id) return false;
  if (current.value.grade_mode === 'self') return true;
  if (current.value.type === 'blank') return state.value.blankInput.trim().length > 0;
  return state.value.selected.length > 0;
});

function blankState() {
  return {
    selected: [],
    blankInput: '',
    essayInput: '',
    submitted: false,
    /** 答案与解析默认隐藏，点「查看解析」后置为 true */
    revealed: false,
    correct: null,
    assessLevel: '',
  };
}

function ensureState(id) {
  if (!cards[id]) cards[id] = blankState();
  return cards[id];
}

/** 清空本次会话（切文档、重新抽题都走它） */
function resetSession() {
  questions.value = [];
  index.value = 0;
  restored.value = false;
  Object.keys(cards).forEach((k) => delete cards[k]);
}

/**
 * 恢复该文档上次的进度。
 *
 * 题号由引擎校验过（`_alive_question_ids`）：重新解析后失效的进度会被丢掉，
 * 也不会串到别的文档。失败不阻塞练习，退回「从头开始」。
 */
async function restoreProgress() {
  const docId = store.currentDocId;
  if (!docId) return false;
  try {
    const p = await api.practiceGetProgress(docId);
    if (!p?.exists || !p.questions?.length) return false;
    questions.value = p.questions;
    index.value = Math.min(p.cursor || 0, p.questions.length - 1);
    mode.value = p.mode || 'sequence';
    if (p.limit) limit.value = p.limit;
    p.questions.forEach((q) => {
      const d = p.drafts?.[String(q.id)] || {};
      cards[q.id] = {
        ...blankState(),
        ...d,
        selected: Array.isArray(d.selected) ? d.selected : [],
      };
    });
    restored.value = true;
    return true;
  } catch (err) {
    console.warn('恢复答题进度失败', err);
    return false;
  }
}

async function openDoc(docId) {
  suspended = true; // 恢复过程中别让中途状态落库
  try {
    resetSession();
    await store.openDocument(docId);
    if (!(await restoreProgress())) applyDefaultLimit();
    await nextTick(); // 等恢复引发的 watcher 跑完再放开
  } finally {
    suspended = false;
  }
}

onMounted(() => openDoc(Number(route.params.docId)));

watch(
  () => route.params.docId,
  (v) => {
    if (v) openDoc(Number(v));
  },
);

/**
 * 进度快照：抽题顺序 + 当前题位 + 每题草稿。
 * 拼成字符串交给 watch 比较，省得对 reactive 对象做深比较。
 */
const snapshot = computed(() => {
  if (!questions.value.length) return '';
  return JSON.stringify({
    ids: questions.value.map((q) => q.id),
    cursor: index.value,
    mode: mode.value,
    limit: limit.value,
    drafts: cards,
  });
});

watch(snapshot, () => scheduleSave());

function scheduleSave() {
  if (suspended) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 600);
}

async function saveNow() {
  clearTimeout(saveTimer);
  saveTimer = null;
  const docId = store.currentDocId;
  if (!docId || !questions.value.length) return;
  try {
    await api.practiceSaveProgress(docId, {
      questionIds: questions.value.map((q) => q.id),
      cursor: index.value,
      mode: mode.value,
      limit: limit.value,
      drafts: cards,
    });
  } catch (err) {
    // 存进度失败不该打断答题，界面上的状态仍在
    console.warn('保存答题进度失败', err);
  }
}

// 防抖窗口内直接离开页面时，别把最后几次作答弄丢
onBeforeUnmount(() => {
  if (saveTimer) saveNow();
});

/** 切题：只改索引，作答状态按题保存 */
function go(target) {
  if (target < 0 || target >= questions.value.length) return;
  index.value = target;
  ensureState(current.value.id);
  startedAt = Date.now();
}

async function start() {
  loading.value = true;
  try {
    const picked = await api.practicePick(store.currentDocId, mode.value, null, limit.value);
    // 重新抽题即开一段新会话，覆盖本文档此前的进度
    resetSession();
    questions.value = picked;
    picked.forEach((q) => ensureState(q.id));
    startedAt = Date.now();
    if (!picked.length) ElMessage.info('当前条件下没有可练习的题目');
  } catch (err) {
    ElMessage.error(`抽题失败：${err.message}`);
  } finally {
    loading.value = false;
  }
}

function onSelect(opt) {
  const s = ensureState(current.value.id);
  if (current.value.type === 'multi') {
    const i = s.selected.indexOf(opt.label);
    if (i >= 0) s.selected.splice(i, 1);
    else s.selected.push(opt.label);
  } else {
    s.selected = [opt.label];
  }
}

function selectJudge(value) {
  ensureState(current.value.id).selected = [value];
}

async function submit() {
  const s = ensureState(current.value.id);
  const answer =
    current.value.type === 'blank'
      ? s.blankInput
      : current.value.grade_mode === 'self'
        ? s.essayInput
        : s.selected.join('');
  try {
    const res = await api.practiceSubmit(current.value.id, answer, Date.now() - startedAt);
    s.submitted = true;
    s.correct = res.correct;
  } catch (err) {
    ElMessage.error(`提交失败：${err.message}`);
  }
}

async function assess(level) {
  const s = ensureState(current.value.id);
  s.assessLevel = level;
  await api.selfAssess(current.value.id, level);
  ElMessage.success(`已记录自评：${level}`);
}

/** 展开本题的答案与解析（按题记忆，来回翻题不会重新藏起来） */
function reveal() {
  ensureState(current.value.id).revealed = true;
}

function openDetail() {
  router.push(`/doc/${store.currentDocId}/questions`);
}
</script>
