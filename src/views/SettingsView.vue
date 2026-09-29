<template>
  <div>
    <div class="qtb-panel">
      <div class="qtb-panel-title">数据位置</div>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="数据目录">
          {{ settings.dataDir }}
        </el-descriptions-item>
        <el-descriptions-item label="数据库">
          {{ paths.db_path }}
        </el-descriptions-item>
        <el-descriptions-item label="图片目录">
          {{ paths.media_dir }}
        </el-descriptions-item>
        <el-descriptions-item label="备份目录">
          {{ paths.backup_dir }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="qtb-row" style="margin-top: 12px">
        <el-button size="small" @click="api.revealDataDir()">打开数据目录</el-button>
        <el-button size="small" @click="reloadPaths">刷新</el-button>
      </div>
      <div class="qtb-muted" style="margin-top: 8px">
        数据目录可整体拷贝到另一台机器使用，题目、批注、答题记录与图片都在其中。
      </div>
    </div>

    <div class="qtb-panel">
      <div class="qtb-panel-title">
        <span>备份与还原</span>
        <el-button size="small" type="primary" :loading="backing" @click="doBackup">
          立即备份
        </el-button>
      </div>

      <el-table :data="backups" size="small" style="width: 100%">
        <el-table-column prop="name" label="备份" min-width="200" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ formatBytes(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" text @click="api.openPath(row.path)">打开</el-button>
            <el-button size="small" text type="primary" @click="doRestore(row)">
              还原
            </el-button>
          </template>
        </el-table-column>
        <template #empty>还没有备份</template>
      </el-table>
    </div>

    <div class="qtb-panel">
      <div class="qtb-panel-title">解析模板</div>
      <el-table :data="store.templates" size="small">
        <el-table-column prop="id" label="模板 ID" width="180" />
        <el-table-column prop="name" label="名称" width="220" />
        <el-table-column prop="description" label="适用场景" />
      </el-table>
      <div class="qtb-muted" style="margin-top: 8px">
        模板是外置的 YAML 文件（engine/templates/），新增题库格式时加一个文件即可，不需要改代码。
      </div>
    </div>

    <div class="qtb-panel">
      <div class="qtb-panel-title">偏好设置</div>
      <el-form label-width="160px" label-position="left" style="max-width: 520px">
        <el-form-item label="连续答对几次移出错题本">
          <el-input-number
            v-model="form.autoRemoveWrongAfter"
            :min="1"
            :max="10"
            @change="savePrefs"
          />
        </el-form-item>
        <el-form-item label="默认解析模板">
          <el-select v-model="form.defaultTemplate" style="width: 260px" @change="savePrefs">
            <el-option
              v-for="t in store.templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </div>

    <div class="qtb-panel">
      <div class="qtb-panel-title">关于</div>
      <div class="qtb-muted" style="line-height: 1.9">
        <div>版本：{{ info.version }}</div>
        <div>
          解析流程：归一化 → 标记 → 回填 → 校验；所有解析结果都带置信度，
          低置信一律进入人工校对队列，不会被静默写入。
        </div>
        <div>
          图片题面按设计只展示原图，由用户手动录入，不引入 OCR。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api';
import { useLibraryStore } from '../stores/library';
import { formatBytes, formatDateTime } from '../utils/format';

const store = useLibraryStore();

const info = ref({});
const paths = ref({});
const backups = ref([]);
const backing = ref(false);
const settings = reactive({ dataDir: '' });
const form = reactive({ autoRemoveWrongAfter: 2, defaultTemplate: 'pdf-consolidated' });

async function reloadPaths() {
  info.value = await api.info();
  paths.value = info.value.paths || {};
  const s = await api.getSettings();
  settings.dataDir = s.dataDir;
  form.autoRemoveWrongAfter = s.autoRemoveWrongAfter;
  form.defaultTemplate = s.defaultTemplate;
}

async function loadBackups() {
  backups.value = await api.listBackups();
}

async function doBackup() {
  backing.value = true;
  try {
    const b = await api.createBackup();
    ElMessage.success(`备份完成：${b.name}`);
    await loadBackups();
  } catch (err) {
    ElMessage.error(`备份失败：${err.message}`);
  } finally {
    backing.value = false;
  }
}

async function doRestore(row) {
  await ElMessageBox.confirm(
    `将用备份「${row.name}」覆盖当前数据。还原前会自动把当前数据库另存一份，但仍建议确认后再继续。`,
    '还原备份',
    { type: 'warning', confirmButtonText: '还原' },
  );
  try {
    await api.restoreBackup(row.path);
    ElMessage.success('已还原');
    await store.loadDocuments();
    await reloadPaths();
  } catch (err) {
    ElMessage.error(`还原失败：${err.message}`);
  }
}

async function savePrefs() {
  await api.updateSettings({
    autoRemoveWrongAfter: form.autoRemoveWrongAfter,
    defaultTemplate: form.defaultTemplate,
  });
  ElMessage.success('已保存');
}

onMounted(async () => {
  await reloadPaths();
  await loadBackups();
});
</script>
