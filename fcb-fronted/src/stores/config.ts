import { defineStore } from 'pinia';
import {ref} from "vue";

export const useConfigStore = defineStore('config', () => {
  const config:any = ref(JSON.parse(localStorage.getItem('config') || '{}') || {}); // 配置
  return { config };
});
