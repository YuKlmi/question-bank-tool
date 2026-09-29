<template>
  <div class="qtb-panel">
    <div class="qtb-panel-title">
      <span>{{ isImageStem ? '手动录入题面（图片题）' : '编辑题目' }}</span>
      <div class="qtb-row">
        <el-button size="small" @click="$emit('cancel')">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="save">
          保存
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="isImageStem"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #title>
        请对照上方原图录入。录入后本题会标为「已修正」，不再出现在待录入队列。
      </template>
    </el-alert>

    <el-form label-width="72px" label-position="left">
      <el-form-item label="题型">
        <el-select v-model="form.type" style="width: 160px">
          <el-option
            v-for="(label, value) in TYPE_LABELS"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>
        <span class="qtb-muted" style="margin-left: 10px">
          判分方式：{{ GRADE_MODE_LABELS[gradeMode] || '-' }}
        </span>
      </el-form-item>

      <el-form-item label="题干">
        <el-input
          v-model="form.stem"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 12 }"
          placeholder="题干文本；填空题的横线可用 ____ 表示"
        />
      </el-form-item>

      <el-form-item label="选项">
        <div style="width: 100%">
          <div
            v-for="(opt, idx) in form.options"
            :key="idx"
            class="qtb-row"
            style="margin-bottom: 8px"
          >
            <el-input v-model="opt.label" style="width: 60px" maxlength="2" />
            <el-input
              v-model="opt.content"
              style="flex: 1"
              :placeholder="`选项 ${opt.label} 的内容`"
            />
            <el-button
              size="small"
              text
              type="danger"
              @click="form.options.splice(idx, 1)"
            >
              删除
            </el-button>
          </div>
          <el-button size="small" @click="addOption">增加选项</el-button>
        </div>
      </el-form-item>

      <el-form-item label="答案">
        <el-input
          v-model="answerText"
          style="width: 320px"
          :placeholder="answerPlaceholder"
        />
        <span class="qtb-muted" style="margin-left: 10px">
          单选/判断填字母；多选连写如 ABC；填空多空用 / 分隔，同义答案用 | 分隔
        </span>
      </el-form-item>

      <el-form-item label="解析">
        <el-input
          v-model="explanationText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 10 }"
          placeholder="可留空"
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import api from '../api';
import { GRADE_MODE_LABELS, TYPE_LABELS } from '../utils/format';

const props = defineProps({
  question: { type: Object, required: true },
});
const emit = defineEmits(['saved', 'cancel']);

const saving = ref(false);
const answerText = ref('');
const explanationText = ref('');

const form = reactive({
  type: 'single',
  stem: '',
  options: [],
});

const isImageStem = computed(
  () => props.question.stem_source === 'image' && !String(props.question.stem || '').trim(),
);

const gradeMode = computed(() => {
  const map = { single: 'auto', multi: 'auto', judge: 'auto', blank: 'semi', essay: 'self' };
  return map[form.type] || 'auto';
});

const answerPlaceholder = computed(() =>
  form.type === 'multi' ? '如 ABC' : form.type === 'blank' ? '如 北京/上海' : '如 A',
);

function loadFrom(q) {
  form.type = q.type || 'single';
  form.stem = q.stem || '';
  form.options = (q.options || []).map((o) => ({
    label: o.label,
    content: o.content || '',
  }));
  if (!form.options.length) {
    form.options = ['A', 'B', 'C', 'D'].map((l) => ({ label: l, content: '' }));
  }
  answerText.value = (q.answer || []).join('');
  explanationText.value = (q.explanations || []).map((e) => e.content || '').join('\n');
}

watch(() => props.question, loadFrom, { immediate: true, deep: false });

function addOption() {
  const next = String.fromCharCode(65 + form.options.length);
  form.options.push({ label: next, content: '' });
}

function parseAnswer(text) {
  const raw = String(text || '').trim();
  if (!raw) return [];
  if (form.type === 'multi') return raw.replace(/[^A-Za-z]/g, '').toUpperCase().split('');
  if (form.type === 'blank') return raw.split('/').map((s) => s.trim()).filter(Boolean);
  return [raw.replace(/[（）()\s]/g, '')];
}

async function save() {
  const opts = form.options.filter((o) => (o.label || '').trim());
  if (!form.stem.trim() && !opts.length) {
    ElMessage.warning('题干与选项不能同时为空');
    return;
  }
  saving.value = true;
  try {
    const payload = {
      type: form.type,
      stem: form.stem,
      options: opts,
      answer: parseAnswer(answerText.value),
    };
    if (explanationText.value.trim()) {
      payload.explanations = [{ title: '解析', content: explanationText.value.trim() }];
    }
    const updated = await api.updateQuestion(props.question.id, payload);
    ElMessage.success('已保存');
    emit('saved', updated);
  } catch (err) {
    ElMessage.error(`保存失败：${err.message}`);
  } finally {
    saving.value = false;
  }
}
</script>
