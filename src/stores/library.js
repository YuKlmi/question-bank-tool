import { defineStore } from 'pinia';
import { ElMessage } from 'element-plus';
import api from '../api';

/**
 * 全局状态：文档列表、当前文档、当前文档的题目与筛选条件。
 *
 * 关键约束（设计原则 1）：所有题目数据都以 currentDocId 为作用域，
 * 切换文档时必须清空上一份文档的题目，避免混排。
 */
export const useLibraryStore = defineStore('library', {
  state: () => ({
    ready: false,
    initError: '',
    paths: {},
    templates: [],

    documents: [],
    loadingDocuments: false,

    currentDocId: null,
    currentDoc: null,
    groups: [],

    questions: [],
    questionTotal: 0,
    loadingQuestions: false,
    filters: {
      groupSeq: null,
      reviewState: null,
      type: null,
      hasAnswer: null,
      keyword: '',
      page: 1,
      pageSize: 20,
    },
  }),

  getters: {
    currentDocName: (s) => s.currentDoc?.name || '',
    pendingInputCount: (s) =>
      s.questions.filter((q) => q.review_state === 'pending_input').length,
  },

  actions: {
    async init() {
      try {
        const info = await api.info();
        this.paths = info.paths || {};
        this.templates = info.templates || [];
        await this.loadDocuments();
        this.ready = true;
      } catch (err) {
        this.initError = err.message;
      }
    },

    async loadDocuments() {
      this.loadingDocuments = true;
      try {
        this.documents = await api.listDocuments();
      } finally {
        this.loadingDocuments = false;
      }
    },

    async importDocument(filePath, templateId) {
      const doc = await api.importDocument(filePath, templateId);
      await this.loadDocuments();
      ElMessage.success(
        `导入完成：共 ${doc.question_count} 题，答案覆盖 ${doc.answered_count} 题`,
      );
      return doc;
    },

    async openDocument(docId) {
      if (this.currentDocId !== docId) {
        this.resetQuestionState();
      }
      this.currentDocId = Number(docId);
      const [doc, groups] = await Promise.all([
        api.getDocument(docId),
        api.docGroups(docId),
      ]);
      this.currentDoc = doc;
      this.groups = groups;
      await this.loadQuestions();
      return doc;
    },

    resetQuestionState() {
      this.questions = [];
      this.questionTotal = 0;
      this.groups = [];
      this.currentDoc = null;
      this.filters = {
        groupSeq: null,
        reviewState: null,
        type: null,
        hasAnswer: null,
        keyword: '',
        page: 1,
        pageSize: 20,
      };
    },

    async loadQuestions() {
      if (!this.currentDocId) return;
      this.loadingQuestions = true;
      try {
        const res = await api.listQuestions(this.currentDocId, this.filters);
        this.questions = res.items;
        this.questionTotal = res.total;
      } finally {
        this.loadingQuestions = false;
      }
    },

    async setFilter(patch) {
      this.filters = { ...this.filters, ...patch, page: patch.page ?? 1 };
      await this.loadQuestions();
    },

    /** 局部更新某题，避免整页刷新丢失滚动位置。 */
    patchQuestion(questionId, updated) {
      const idx = this.questions.findIndex((q) => q.id === questionId);
      if (idx >= 0) this.questions[idx] = { ...this.questions[idx], ...updated };
    },

    async refreshCurrentDoc() {
      if (!this.currentDocId) return;
      this.currentDoc = await api.getDocument(this.currentDocId);
      await this.loadDocuments();
    },
  },
});
