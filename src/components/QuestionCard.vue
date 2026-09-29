<template>
  <div>
    <!-- 图片题面：原样展示原图（保真优先，不做 OCR 重建） -->
    <div v-if="isImageStem" class="qtb-panel" style="padding: 12px; background: #fffdf6">
      <el-alert
        v-if="editable"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 10px"
      >
        <template #title>
          本题题面是图片，原文没有文本层。可对照下图手动录入题干与选项。
        </template>
      </el-alert>
      <div class="qtb-images">
        <el-image
          v-for="img in stemImages"
          :key="img.id"
          class="qtb-image qtb-image--stem"
          :src="mediaUrl(img.file_path)"
          :preview-src-list="stemImages.map((i) => mediaUrl(i.file_path))"
          fit="contain"
          preview-teleported
        />
      </div>
    </div>

    <!-- 题干 -->
    <div v-if="question.stem" class="qtb-stem">{{ question.stem }}</div>

    <!-- 题干配图（非纯图片题时紧跟在题干后） -->
    <div v-if="!isImageStem && stemImages.length" class="qtb-images">
      <el-image
        v-for="img in stemImages"
        :key="img.id"
        class="qtb-image"
        :src="mediaUrl(img.file_path)"
        :preview-src-list="stemImages.map((i) => mediaUrl(i.file_path))"
        fit="contain"
        preview-teleported
      />
    </div>

    <!-- 选项 -->
    <div v-if="question.options && question.options.length" style="margin-top: 12px">
      <div
        v-for="opt in question.options"
        :key="opt.id || opt.label"
        class="qtb-option"
        :class="optionClass(opt)"
        @click="onOptionClick(opt)"
      >
        <span class="qtb-option-label">{{ opt.label }}</span>
        <span class="qtb-option-content">
          <template v-if="opt.content">{{ opt.content }}</template>
          <el-image
            v-if="opt.image_path"
            class="qtb-image"
            :src="mediaUrl(opt.image_path)"
            fit="contain"
          />
          <span v-if="!opt.content && !opt.image_path" class="qtb-muted">（空）</span>
        </span>
        <el-icon v-if="showAnswer && isCorrectOption(opt)" color="#67c23a"><CircleCheck /></el-icon>
      </div>
    </div>

    <!-- 答案区 -->
    <div v-if="showAnswer" class="qtb-answer-box">
      <strong>答案：</strong>
      <span v-if="question.answer && question.answer.length">
        {{ question.answer.join('、') }}
      </span>
      <span v-else class="qtb-muted">文档中未检出答案（已进入待校对队列）</span>
      <span
        v-if="question.answer_source"
        class="qtb-muted"
        style="margin-left: 8px"
      >
        （来源：{{ answerSourceLabel(question.answer_source) }}）
      </span>
    </div>

    <!-- 解析 -->
    <div
      v-for="exp in question.explanations || []"
      :key="exp.id"
      class="qtb-explain-box"
    >
      <strong>{{ exp.title || '解析' }}</strong>
      <div v-if="exp.content" style="margin-top: 4px">{{ exp.content }}</div>
      <div v-if="expImages(exp).length" class="qtb-images">
        <el-image
          v-for="img in expImages(exp)"
          :key="img.id"
          class="qtb-image"
          :src="mediaUrl(img.file_path)"
          fit="contain"
          style="max-height: 360px"
        />
      </div>
    </div>

    <!-- 文档原始批注 -->
    <div v-if="docComments.length" class="qtb-explain-box">
      <strong>文档原始批注</strong>
      <div v-for="(c, i) in docComments" :key="i" style="margin-top: 4px">
        <span class="qtb-muted">[{{ c.author || '匿名' }}]</span> {{ c.comment_text }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { mediaUrl } from '../utils/media';
import { answerSourceLabel } from '../utils/format';

const props = defineProps({
  question: { type: Object, required: true },
  /** 展示已选答案 */
  selected: { type: Array, default: () => [] },
  /** 是否展示答案与解析 */
  showAnswer: { type: Boolean, default: true },
  /** 是否可交互选择选项 */
  interactive: { type: Boolean, default: false },
  /** 是否展示「手动录入」提示 */
  editable: { type: Boolean, default: false },
  /** 判分结果：true/false/null */
  correct: { type: Boolean, default: null },
});

const emit = defineEmits(['select', 'toggle-option']);

const stemImages = computed(() =>
  (props.question.images || []).filter((i) => i.role === 'stem' || i.role === 'option'),
);

const isImageStem = computed(
  () => props.question.stem_source === 'image' && !String(props.question.stem || '').trim(),
);

const docComments = computed(() => props.question.doc_comments || []);

function expImages(exp) {
  const paths = new Set(exp.imagePaths || []);
  return (props.question.images || []).filter(
    (i) => i.role === 'explanation' && paths.has(i.file_path),
  );
}

function isCorrectOption(opt) {
  return (props.question.answer || []).includes(opt.label);
}

function optionClass(opt) {
  const cls = [];
  if (props.selected.includes(opt.label)) cls.push('is-selected');
  if (props.showAnswer && props.correct !== null) {
    if (isCorrectOption(opt)) cls.push('is-correct');
    else if (props.selected.includes(opt.label)) cls.push('is-wrong');
  }
  return cls;
}

function onOptionClick(opt) {
  if (!props.interactive) return;
  emit('select', opt);
}
</script>
