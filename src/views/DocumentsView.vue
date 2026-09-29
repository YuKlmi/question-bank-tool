<template>
  <div>
    <div class="qtb-panel">
      <div class="qtb-panel-title">
        <span>导入题库文档</span>
        <span class="qtb-muted">
          支持 .doc / .docx / .pdf（文本型）。题目按文档分区存储，互不混淆。
        </span>
      </div>
      <div class="qtb-row">
        <el-button type="primary" :loading="importing" @click="doImport">
          <el-icon style="margin-right: 4px"><Upload /></el-icon>
          选择文档并导入
        </el-button>
        <el-select
          v-model="templateId"
          placeholder="解析模板（默认按扩展名自动选择）"
          clearable
          style="width: 300px"
        >
          <el-option
            v-for="t in store.templates"
            :key="t.id"
            :label="`${t.name}（${t.id}）`"
            :value="t.id"
          />
        </el-select>
        <el-button @click="store.loadDocuments()" :loading="store.loadingDocuments">
          刷新
        </el-button>
      </div>
      <div v-if="store.templates.length" class="qtb-muted" style="margin-top: 10px">
        <div v-for="t in store.templates" :key="t.id">
          <span class="qtb-code">{{ t.id }}</span> {{ t.name }} —— {{ t.description }}
        </div>
      </div>
    </div>

    <div v-if="!store.documents.length" class="qtb-panel">
      <div class="qtb-empty">
        <p>还没有导入任何题库。</p>
        <p class="qtb-muted">
          点击上方「选择文档并导入」开始。导入后可以进入文档浏览题目、做题并记录批注。
        </p>
      </div>
    </div>

    <el-row :gutter="14">
      <el-col v-for="doc in store.documents" :key="doc.id" :xs="24" :lg="12">
        <div class="qtb-panel">
          <div class="qtb-panel-title">
            <span :title="doc.name" style="overflow: hidden; text-overflow: ellipsis">
              <el-icon style="margin-right: 6px"><Document /></el-icon>{{ doc.name }}
            </span>
            <el-tag size="small" type="info" effect="plain">
              {{ doc.orig_type.toUpperCase() }}
            </el-tag>
          </div>

          <div class="qtb-row" style="margin-bottom: 10px">
            <el-statistic title="题目" :value="doc.question_count" />
            <el-statistic title="已匹配答案" :value="doc.answered_count" />
            <el-statistic
              title="答案覆盖"
              :value="coverage(doc)"
              suffix="%"
            />
          </div>

          <div class="qtb-row" style="margin-bottom: 12px">
            <el-tag v-if="doc.pending_input" type="warning" size="small">
              待录入 {{ doc.pending_input }}
            </el-tag>
            <el-tag v-if="doc.pending_review" type="danger" size="small">
              待校对 {{ doc.pending_review }}
            </el-tag>
            <el-tag v-if="!doc.pending_input && !doc.pending_review" type="success" size="small">
              全部就绪
            </el-tag>
            <span class="qtb-muted">导入于 {{ formatDateTime(doc.created_at) }}</span>
          </div>

          <div v-if="warnings(doc).length" style="margin-bottom: 10px">
            <el-alert type="warning" :closable="false" show-icon>
              <template #title>
                <div v-for="(w, i) in warnings(doc)" :key="i">{{ w }}</div>
              </template>
            </el-alert>
          </div>

          <div class="qtb-row">
            <el-button type="primary" size="small" @click="open(doc, 'questions')">
              浏览与校对
            </el-button>
            <el-button size="small" @click="open(doc, 'practice')">开始答题</el-button>
            <el-dropdown size="small" @command="(c) => onCommand(c, doc)">
              <el-button size="small">
                更多<el-icon><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="reparse">重新解析</el-dropdown-item>
                  <el-dropdown-item command="markdown">导出 Markdown</el-dropdown-item>
                  <el-dropdown-item command="csv">导出 CSV</el-dropdown-item>
                  <el-dropdown-item command="source">打开原文件</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除此文档</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </el-col>
    </el-row>

    <div v-if="store.documents.length" class="qtb-panel">
      <div class="qtb-panel-title">解析概况</div>
      <div class="qtb-muted" style="line-height: 1.9">
        <div v-for="doc in store.documents" :key="doc.id">
          <strong>{{ doc.name }}</strong>：
          共 {{ doc.question_count }} 题，
          命中答案 {{ doc.answered_count }} 题（{{ coverage(doc) }}%），
          图片题待录入 {{ doc.pending_input }} 题，
          待校对 {{ doc.pending_review }} 题。
          <template v-if="doc.parse_report && doc.parse_report.answers_needs_confirm">
            其中 {{ doc.parse_report.answers_needs_confirm }} 条答案为就近推断，需人工确认。
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api';
import { useLibraryStore } from '../stores/library';
import { formatDateTime } from '../utils/format';

const store = useLibraryStore();
const router = useRouter();
const importing = ref(false);
const templateId = ref('');

function coverage(doc) {
  if (!doc.question_count) return 0;
  return Math.round((doc.answered_count / doc.question_count) * 100);
}

function warnings(doc) {
  return (doc.parse_report && doc.parse_report.warnings) || [];
}

async function doImport() {
  const files = await api.pickFile();
  if (!files || !files.length) return;
  importing.value = true;
  try {
    for (const f of files) {
      try {
        await store.importDocument(f, templateId.value || undefined);
      } catch (err) {
        ElMessage.error(`导入失败（${f}）：${err.message}`);
      }
    }
  } finally {
    importing.value = false;
  }
}

function open(doc, route) {
  router.push(`/doc/${doc.id}/${route}`);
}

async function onCommand(command, doc) {
  if (command === 'reparse') {
    await ElMessageBox.confirm(
      '重新解析会按当前模板重跑一遍解析。手动录入的答案会被保留，其余解析结果将重建。',
      '重新解析',
      { type: 'warning' },
    );
    const updated = await api.reparseDocument(doc.id);
    await store.loadDocuments();
    ElMessage.success(`重新解析完成：${updated.question_count} 题`);
    return;
  }

  if (command === 'markdown' || command === 'csv') {
    const ext = command === 'csv' ? 'csv' : 'md';
    const target = await api.pickSavePath({
      defaultName: `${doc.name.replace(/\.[^.]+$/, '')}.${ext}`,
      filters: [
        command === 'csv'
          ? { name: 'CSV', extensions: ['csv'] }
          : { name: 'Markdown', extensions: ['md'] },
      ],
    });
    if (!target) return;
    if (command === 'csv') await api.exportCsv(doc.id, target);
    else await api.exportMarkdown(doc.id, target);
    ElMessage.success('导出完成');
    return;
  }

  if (command === 'source') {
    if (!doc.src_path) {
      ElMessage.warning('没有记录原文件路径');
      return;
    }
    await api.showItem(doc.src_path);
    return;
  }

  if (command === 'delete') {
    await ElMessageBox.confirm(
      `确定删除「${doc.name}」及其全部题目、批注与答题记录？此操作不可撤销。`,
      '删除文档',
      { type: 'warning', confirmButtonText: '删除' },
    );
    await api.deleteDocument(doc.id, true);
    await store.loadDocuments();
    ElMessage.success('已删除');
  }
}
</script>
