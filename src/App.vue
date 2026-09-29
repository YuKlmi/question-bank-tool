<template>
  <div v-if="store.initError" class="qtb-layout">
    <div class="qtb-empty" style="margin: auto; max-width: 620px">
      <el-result icon="error" title="无法连接解析引擎" :sub-title="store.initError">
        <template #extra>
          <el-alert type="info" :closable="false" show-icon>
            <p>请确认已通过 Electron 启动（<span class="qtb-code">npm run dev</span> 或
              <span class="qtb-code">npm start</span>），且本机已安装 Python 3。</p>
          </el-alert>
        </template>
      </el-result>
    </div>
  </div>

  <div v-else class="qtb-layout">
    <aside class="qtb-sidebar">
      <div class="qtb-brand">题库存取练习工具</div>
      <nav class="qtb-nav">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          class="qtb-nav-item"
          :class="{ 'is-active': isActive(item) }"
          :to="item.to"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
          <span v-if="item.badge" class="qtb-muted" style="margin-left: auto">
            {{ item.badge }}
          </span>
        </router-link>
      </nav>
      <div style="padding: 12px 16px; border-top: 1px solid var(--qtb-border)">
        <div class="qtb-muted" style="line-height: 1.6">
          共 {{ store.documents.length }} 份文档
        </div>
      </div>
    </aside>

    <main class="qtb-main">
      <header class="qtb-header">
        <div class="qtb-header-title">
          {{ pageTitle }}
        </div>
        <div class="qtb-row">
          <el-tag v-if="store.currentDoc && isDocScoped" type="info" effect="plain" size="small">
            当前文档：{{ store.currentDoc.name }}
          </el-tag>
          <el-button
            v-if="store.currentDoc && isDocScoped"
            size="small"
            @click="router.push('/documents')"
          >
            返回文档库
          </el-button>
        </div>
      </header>

      <section class="qtb-content">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useLibraryStore } from './stores/library';

const store = useLibraryStore();
const route = useRoute();
const router = useRouter();

const navItems = computed(() => [
  { name: 'documents', label: '文档库', icon: 'Files', to: '/documents' },
  { name: 'wrongbook', label: '错题本', icon: 'Warning', to: '/wrongbook' },
  { name: 'starred', label: '收藏与复习', icon: 'Star', to: '/starred' },
  { name: 'settings', label: '设置与数据', icon: 'Setting', to: '/settings' },
]);

const isDocScoped = computed(() =>
  ['questions', 'practice'].includes(route.name),
);

const pageTitle = computed(() => {
  const title = route.meta?.title || '';
  if (isDocScoped.value && store.currentDoc) {
    return `${store.currentDoc.name} · ${title}`;
  }
  return title || '题库';
});

function isActive(item) {
  if (item.name === 'documents') {
    return ['documents', 'questions', 'practice'].includes(route.name);
  }
  return route.name === item.name;
}

onMounted(() => {
  store.init();
});
</script>
