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
        <el-input-number v-model="limit" :min="1" :max="100" />
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
          <el-progress
            :percentage="Math.round(((index + 1) / questions.length) * 100)"
            style="flex: 1"
            :show-text="false"
          />
          <el-tag size="small" effect="plain">{{ typeLabel(current.type) }}</el-tag>
          <el-tag v-if="current.display_no" size="small" type="info" effect="plain">
            原题号 {{ current.display_no }}
          </el-tag>
        </div>

        <!-- 判断题：用对/错两键作答 -->
        <QuestionCard
          v-if="current.type === 'judge'"
          :question="current"
          :selected="selected"
          :show-answer="submitted"
          :correct="correct"
        />
        <div v-if="current.type === 'judge' && !submitted" class="qtb-row" style="margin-top: 12px">
          <el-button type="success" size="large" @click="selectJudge('对')">对</el-button>
          <el-button type="danger" size="large" @click="selectJudge('错')">错</el-button>
        </div>

        <!-- 填空题：多空用 / 分隔 -->
        <template v-else-if="current.type === 'blank'">
          <QuestionCard
            :question="current"
            :selected="selected"
            :show-answer="submitted"
            :correct="correct"
          />
          <el-input
            v-model="blankInput"
            :disabled="submitted"
            placeholder="多个空用 / 分隔，例如：北京/上海"
            style="margin-top: 12px"
          />
        </template>

        <!-- 选择题 -->
        <QuestionCard
          v-else
          :question="current"
          :selected="selected"
          :show-answer="submitted"
          :interactive="!submitted"
          :correct="correct"
          @select="onSelect"
        />

        <!-- 主观题：不自动判分 -->
        <div v-if="current.grade_mode === 'self'" style="margin-top: 12px">
          <el-input
            v-model="essayInput"
            :disabled="submitted"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="写下你的作答（不自动判分，提交后对照参考答案自评）"
          />
          <div v-if="submitted" class="qtb-row" style="margin-top: 10px">
            <span>自评：</span>
            <el-button
              v-for="level in ['掌握', '模糊', '不会']"
              :key="level"
              size="small"
              :type="assessLevel === level ? 'primary' : 'default'"
              @click="assess(level)"
            >
              {{ level }}
            </el-button>
          </div>
        </div>

        <div class="qtb-row" style="margin-top: 16px">
          <el-button
            v-if="!submitted"
            type="primary"
            :disabled="!canSubmit"
            @click="submit"
          >
            提交并对照答案
          </el-button>
          <template v-else>
            <el-result
              v-if="correct !== null"
              :icon="correct ? 'success' : 'error'"
              :title="correct ? '答对了' : '答错了'"
              style="padding: 0"
            />
            <el-button type="primary" @click="next">下一题</el-button>
            <el-button @click="prev" :disabled="index === 0">上一题</el-button>
          </template>
          <div class="qtb-spacer" />
          <el-button text @click="openDetail">查看题目详情</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
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
const limit = ref(20);
const loading = ref(false);
const questions = ref([]);
const index = ref(0);

const selected = ref([]);
const blankInput = ref('');
const essayInput = ref('');
const submitted = ref(false);
const correct = ref(null);
const assessLevel = ref('');
let startedAt = Date.now();

const current = computed(() => questions.value[index.value] || {});

const canSubmit = computed(() => {
  if (current.value.grade_mode === 'self') return true;
  if (current.value.type === 'blank') return blankInput.value.trim().length > 0;
  return selected.value.length > 0;
});

onMounted(async () => {
  await store.openDocument(Number(route.params.docId));
});

watch(
  () => route.params.docId,
  async (v) => {
    questions.value = [];
    if (v) await store.openDocument(Number(v));
  },
);

function resetAnswer() {
  selected.value = [];
  blankInput.value = '';
  essayInput.value = '';
  submitted.value = false;
  correct.value = null;
  assessLevel.value = '';
  startedAt = Date.now();
}

async function start() {
  loading.value = true;
  try {
    const picked = await api.practicePick(
      store.currentDocId,
      mode.value,
      null,
      limit.value,
    );
    questions.value = picked;
    index.value = 0;
    resetAnswer();
    if (!picked.length) ElMessage.info('当前条件下没有可练习的题目');
  } catch (err) {
    ElMessage.error(`抽题失败：${err.message}`);
  } finally {
    loading.value = false;
  }
}

function onSelect(opt) {
  if (current.value.type === 'multi') {
    const i = selected.value.indexOf(opt.label);
    if (i >= 0) selected.value.splice(i, 1);
    else selected.value.push(opt.label);
  } else {
    selected.value = [opt.label];
  }
}

function selectJudge(value) {
  selected.value = [value];
}

async function submit() {
  const answer =
    current.value.type === 'blank'
      ? blankInput.value
      : current.value.grade_mode === 'self'
        ? essayInput.value
        : selected.value.join('');
  try {
    const res = await api.practiceSubmit(current.value.id, answer, Date.now() - startedAt);
    submitted.value = true;
    correct.value = res.correct;
  } catch (err) {
    ElMessage.error(`提交失败：${err.message}`);
  }
}

async function assess(level) {
  assessLevel.value = level;
  await api.selfAssess(current.value.id, level);
  ElMessage.success(`已记录自评：${level}`);
}

function next() {
  if (index.value < questions.value.length - 1) {
    index.value += 1;
    resetAnswer();
  } else {
    ElMessage.success('本轮练习完成');
  }
}

function prev() {
  if (index.value > 0) {
    index.value -= 1;
    resetAnswer();
  }
}

function openDetail() {
  router.push(`/doc/${store.currentDocId}/questions`);
}
</script>
