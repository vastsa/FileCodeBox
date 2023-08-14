import { defineStore } from 'pinia';
import {ref} from "vue";

export const useFileBoxStore = defineStore('fileBox', () => {
  const showFileBox = ref(false);
  return { showFileBox };
});
