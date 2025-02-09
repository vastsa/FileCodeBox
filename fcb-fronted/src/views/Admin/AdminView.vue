<template>
  <el-container v-if="adminData.isAdmin" style="height: 100vh;width: 100vw;position: relative;user-select: none">
    <el-header>
      <el-menu mode="horizontal" router :default-active="route.path">
        <el-menu-item v-for="menu in menus" :index="menu.path" :key="menu.path">{{menu.name}}</el-menu-item>
        <el-menu-item style="float: right" @click="toggleDark(!isDark)">{{ t('admin.menu.color') }}</el-menu-item>
        <el-menu-item style="float: right" @click="logout()">{{ t('admin.menu.signout') }}</el-menu-item>
      </el-menu>
    </el-header>
    <el-main>
      <router-view/>
    </el-main>
  </el-container>
  <el-form size="large" v-else>
    <el-form-item :label="t('admin.login.managePassword')">
      <el-input
          v-model="adminData.adminPassword"
          :placeholder="t('admin.login.passwordNotEmpty')"
          type="password"
      >
        <template #append>
          <el-button @click="refreshLoginStatus">{{ t('admin.login.login') }}</el-button>
        </template>
      </el-input>
    </el-form-item>
  </el-form>
</template>
<script setup lang="ts">
import { useDark, useToggle } from '@vueuse/core';
import { ref } from "vue";
const isDark = useDark()
const toggleDark = useToggle(isDark)
import { useRoute } from 'vue-router';
import { useAdminData } from "@/stores/adminData";
import { request } from "@/utils/request";
import { ElMessage } from "element-plus";

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const adminData = useAdminData();
const route = useRoute();
const menus = ref([
  {
    name: t('admin.menu.fileManage'),
    path: '/admin',
  },
  {
    name: t('admin.menu.systemSetting'),
    path: '/admin/setting',
  },
  {
    name: t('admin.menu.local'),
    path: '/admin/local',
  },
  {
    name: t('admin.menu.about'),
    path: '/admin/about',
  },
  {
    name: t('admin.menu.send'),
    path: '/#/send',
  },
  {
    name: t('admin.menu.receive'),
    path: '/#/',
  },
]);
const refreshLoginStatus = () => {
  request({
    url: '/admin/login',
    method: 'post',
    data: {
      password: adminData.adminPassword,
    },
  }).then((res: any) => {
    if (res.code === 200) {
      adminData.updateAdminPwd(res.detail.token);
      ElMessage.success(t('admin.login.loginSuccess'));
    } else {
      localStorage.clear();
      ElMessage.error(t('admin.login.loginError'));
    }
  });
};
const logout = () => {
  localStorage.clear();
};

</script>
<style lang="scss" scoped>
</style>