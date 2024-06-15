import { defineStore } from 'pinia';
import {reactive} from "vue";

export const useFileDataStore = defineStore('fileData', () => {
  const receiveData = reactive(JSON.parse(localStorage.getItem('receiveData')||'[]') || []); // 接收的数据
  const shareData = reactive(JSON.parse(localStorage.getItem('shareData')||'[]') || []); // 接收的数据
  function save() {
    localStorage.setItem('receiveData', JSON.stringify(receiveData));
    localStorage.setItem('shareData', JSON.stringify(shareData));
  }
  function addReceiveData(data:any) {
    receiveData.unshift(data);
    save();
  }

  function addShareData(data:any) {
    shareData.unshift(data);
    save();
  }

  function deleteReceiveData(index: number) {
    receiveData.splice(index, 1);
    save();
  }

  function deleteShareData(index: number) {
    shareData.splice(index, 1);
    save();
  }
  return { receiveData, shareData, save, addShareData, addReceiveData, deleteReceiveData, deleteShareData };
});