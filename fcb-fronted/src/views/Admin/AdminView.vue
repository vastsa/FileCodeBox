<template>
  <el-container v-if="isLogin" style="height: 100vh;width: 100vw;position: relative;user-select: none">
    <el-header>
      <el-menu mode="horizontal" router :default-active="route.path">
        <el-menu-item v-for="menu in menus" :index="menu.path" :key="menu.path">{{menu.name}}</el-menu-item>
        <el-menu-item style="float: right" @click="toggleDark(!isDark)">颜色模式</el-menu-item>
        <el-menu-item style="float: right" @click="adminData.updateAdminPwd('');isLogin=false">注销登录</el-menu-item>
      </el-menu>
    </el-header>
    <el-main>
      <router-view/>
    </el-main>
  </el-container>
  <el-form size="large" v-else>
    <el-form-item label="管理密码">
      <el-input
          v-model="adminData.adminPassword"
          placeholder="请输入密码！"
          type="password"
      >
        <template #append>
          <el-button @click="refreshLoginStatus">登录</el-button>
        </template>
      </el-input>
    </el-form-item>
  </el-form>
</template>
<script setup lang="ts">
import { useDark, useToggle } from '@vueuse/core';
import { ref } from "vue";
const isDark = useDark()
const isLogin = ref(false);
const toggleDark = useToggle(isDark)
import { useRoute } from 'vue-router';
import { useAdminData } from "@/stores/adminData";
import { request } from "@/utils/request";
import { ElMessage } from "element-plus";

const adminData = useAdminData();
const route = useRoute();
const menus = ref([
  {
    name: '文件管理',
    path: '/admin',
  },
  {
    name: '系统设置',
    path: '/admin/setting',
  },
  {
    name: '关于我们',
    path: '/admin/about',
  }
]);
const refreshLoginStatus = () => {
  adminData.updateAdminPwd(adminData.adminPassword);
  request({
    url: '/admin/login',
    method: 'post',
  }).then((res: any) => {
    if (res.code === 200) {
      isLogin.value = true;
      ElMessage.success('登录成功！');
    } else {
      ElMessage.error(res.detail);
    }
  });
};
refreshLoginStatus();
</script>
<style lang="scss" scoped>
</style>