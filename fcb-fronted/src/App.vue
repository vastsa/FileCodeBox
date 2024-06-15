<script setup lang="ts">
import { onMounted } from "vue";
import { request } from "@/utils/request";

onMounted(() => {
  request({
    url:'/',
    method:'post'
  }).then((res:any)=>{
    if (res.code === 200) {
      localStorage.setItem('config', JSON.stringify(res.detail));
    }
  })
});
</script>

<template>
  <div>
    <RouterView />
  </div>
</template>

<style scoped></style>
