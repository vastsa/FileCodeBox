<script setup lang="ts">
import { onMounted } from "vue";
import { request } from "@/utils/request";
import { ElNotification } from 'element-plus'
onMounted(() => {
  request({
    url:'/',
    method:'post'
  }).then((res:any)=>{
    if (res.code === 200) {
      localStorage.setItem('config', JSON.stringify(res.detail));
      if (res.detail.notify_title && res.detail.notify_content && localStorage.getItem('notify') !== res.detail.notify_title + res.detail.notify_content) {
        localStorage.setItem('notify', res.detail.notify_title + res.detail.notify_content);
        ElNotification({
          title: res.detail.notify_title,
          dangerouslyUseHTMLString: true,
          message: res.detail.notify_content,
          type: 'success'
        });
      }
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
