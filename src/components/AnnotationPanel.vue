<template>
  <div style="margin-top: 10px">
    <div class="qtb-row" style="margin-bottom: 8px">
      <strong>我的批注（{{ annotations.length }}）</strong>
      <div class="qtb-spacer" />
      <el-button size="small" text type="primary" @click="adding = !adding">
        {{ adding ? '收起' : '添加批注' }}
      </el-button>
    </div>

    <div v-if="adding" style="margin-bottom: 10px">
      <el-input
        v-model="draft"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="写下这题的思路、易错点或复习提示…"
      />
      <div class="qtb-row" style="margin-top: 8px">
        <el-color-picker v-model="color" size="small" />
        <div class="qtb-spacer" />
        <el-button size="small" @click="cancel">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="submit">
          保存
        </el-button>
      </div>
    </div>

    <div v-if="!annotations.length && !adding" class="qtb-muted">暂无批注</div>

    <div
      v-for="a in annotations"
      :key="a.id"
      class="qtb-panel"
      style="padding: 10px; margin-bottom: 8px"
    >
      <div class="qtb-row" style="align-items: flex-start">
        <el-icon :color="a.color || '#909399'" style="margin-top: 3px"><ChatDotSquare /></el-icon>
        <div style="flex: 1; white-space: pre-wrap; word-break: break-word">
          {{ a.content }}
        </div>
        <el-button size="small" text type="danger" @click="remove(a)">删除</el-button>
      </div>
      <div class="qtb-muted" style="margin-top: 4px">
        {{ a.created_at ? a.created_at.replace('T', ' ').slice(0, 16) : '' }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api';

const props = defineProps({
  questionId: { type: Number, required: true },
  annotations: { type: Array, default: () => [] },
});
const emit = defineEmits(['changed']);

const adding = ref(false);
const saving = ref(false);
const draft = ref('');
const color = ref('#409eff');

function cancel() {
  adding.value = false;
  draft.value = '';
}

async function submit() {
  const text = draft.value.trim();
  if (!text) {
    ElMessage.warning('批注内容不能为空');
    return;
  }
  saving.value = true;
  try {
    await api.createAnnotation(props.questionId, text, 'note', color.value);
    draft.value = '';
    adding.value = false;
    ElMessage.success('批注已添加');
    emit('changed');
  } catch (err) {
    ElMessage.error(`添加失败：${err.message}`);
  } finally {
    saving.value = false;
  }
}

async function remove(a) {
  await ElMessageBox.confirm('删除这条批注？', '确认', { type: 'warning' });
  await api.deleteAnnotation(a.id);
  ElMessage.success('已删除');
  emit('changed');
}
</script>
