<template>
  <div ref="el" :style="{ height: height + 'px', width: '100%' }" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as echarts from 'echarts';

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: Number, default: 220 },
});

const el = ref(null);
let chart = null;

function render() {
  if (!el.value) return;
  if (!chart) chart = echarts.init(el.value);
  chart.setOption(props.option, true);
}

function resize() {
  if (chart) chart.resize();
}

onMounted(() => {
  render();
  window.addEventListener('resize', resize);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize);
  if (chart) {
    chart.dispose();
    chart = null;
  }
});

watch(() => props.option, render, { deep: true });
</script>
