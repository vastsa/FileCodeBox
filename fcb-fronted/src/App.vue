<script setup lang="ts">
import { onMounted } from "vue";
import { request } from "@/utils/request";
import { ElNotification } from 'element-plus'
import { useConfigStore } from "@/stores/config";

const { config } = useConfigStore();
onMounted(() => {
  request({
    url:'/',
    method:'post'
  }).then((res:any)=>{
    if (res.code === 200) {
      localStorage.setItem('config', JSON.stringify(res.detail));
      if (config.notify_title && config.notify_content && localStorage.getItem('notify') !== config.notify_title + config.notify_content) {
        localStorage.setItem('notify', config.notify_title + config.notify_content);
        ElNotification({
          title: config.notify_title,
          dangerouslyUseHTMLString: true,
          message: config.notify_content,
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
