import { createRouter, createWebHashHistory } from 'vue-router';

/**
 * 用 hash 路由：打包后是 file:// 加载，history 模式会 404。
 *
 * 路由结构体现「文档是最外层容器」：
 *   /documents            → 文档库（最外层）
 *   /doc/:docId/questions → 某份文档下的题目（校对 / 浏览）
 *   /doc/:docId/practice  → 某份文档下答题
 * 错题本与收藏是跨文档的聚合视图，但都显示来源文档。
 */
const routes = [
  { path: '/', redirect: '/documents' },
  {
    path: '/documents',
    name: 'documents',
    component: () => import('./views/DocumentsView.vue'),
    meta: { title: '文档库' },
  },
  {
    path: '/doc/:docId/questions',
    name: 'questions',
    component: () => import('./views/QuestionsView.vue'),
    meta: { title: '题目与校对' },
  },
  {
    path: '/doc/:docId/practice',
    name: 'practice',
    component: () => import('./views/PracticeView.vue'),
    meta: { title: '答题' },
  },
  {
    path: '/wrongbook',
    name: 'wrongbook',
    component: () => import('./views/WrongbookView.vue'),
    meta: { title: '错题本' },
  },
  {
    path: '/starred',
    name: 'starred',
    component: () => import('./views/StarredView.vue'),
    meta: { title: '收藏与复习' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('./views/SettingsView.vue'),
    meta: { title: '设置与数据' },
  },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
});
