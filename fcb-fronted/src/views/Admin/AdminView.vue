<template>
  <el-container style="height: 100vh;width: 100vw;position: relative;user-select: none">
    <el-header>
      <el-menu mode="horizontal" router :default-active="route.path">
        <el-menu-item v-for="menu in menus" :index="menu.path" :key="menu.path">{{menu.name}}</el-menu-item>
      </el-menu>
    </el-header>
    <el-main>
      <router-view/>
    </el-main>
  </el-container>
</template>
<script setup lang="ts">
import { useDark } from '@vueuse/core';
import { ref } from "vue";
const isDark = useDark()
import { useRoute } from 'vue-router';
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
console.log(isDark.value);
</script>
<style lang="scss" scoped>
</style>