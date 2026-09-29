/** 界面展示用的枚举文案与格式化。 */

export const TYPE_LABELS = {
  single: '单选',
  multi: '多选',
  judge: '判断',
  blank: '填空',
  essay: '简答',
};

export const GRADE_MODE_LABELS = {
  auto: '自动判分',
  semi: '半自动',
  self: '自评',
};

export const REVIEW_STATE_LABELS = {
  pending_input: '待录入',
  pending: '待校对',
  ok: '已通过',
  fixed: '已修正',
};

export const REVIEW_STATE_TAG = {
  pending_input: 'warning',
  pending: 'danger',
  ok: 'success',
  fixed: 'primary',
};

export const ANSWER_SOURCE_LABELS = {
  doc: '文档内嵌',
  doc_inferred: '就近推断',
  external: '外部文件',
  manual: '手动录入',
};

export const PRACTICE_MODES = [
  { value: 'sequence', label: '顺序练习' },
  { value: 'random', label: '随机练习' },
  { value: 'pending', label: '待录入题（图片题）' },
  { value: 'wrong', label: '错题重做' },
  { value: 'starred', label: '收藏题' },
];

export function typeLabel(t) {
  return TYPE_LABELS[t] || t || '未知';
}

export function reviewStateLabel(s) {
  return REVIEW_STATE_LABELS[s] || s || '';
}

export function answerSourceLabel(s) {
  return ANSWER_SOURCE_LABELS[s] || s || '';
}

export function formatBytes(n) {
  if (!n && n !== 0) return '-';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDateTime(value) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 19);
}

export function confidenceText(v) {
  if (v === null || v === undefined) return '-';
  return `${Math.round(Number(v) * 100)}%`;
}
