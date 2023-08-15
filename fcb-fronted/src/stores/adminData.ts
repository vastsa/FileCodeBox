import { defineStore } from 'pinia';
import {ref} from "vue";

export const useAdminData = defineStore('adminData', () => {
  const adminPassword = ref(localStorage.getItem('adminPassword') || '');
  function updateAdminPwd(pwd: string) {
    adminPassword.value = pwd;
    localStorage.setItem('adminPassword', pwd);
  }
  return { adminPassword,updateAdminPwd };
});
