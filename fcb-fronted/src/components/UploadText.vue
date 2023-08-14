<script setup lang="ts">
import { ref } from 'vue'
import { request } from "@/utils/request";
const shareText = ref('')
import { useFileDataStore } from "@/stores/fileData";
import { useFileBoxStore } from "@/stores/fileBox";
const fileBoxStore = useFileBoxStore();
const fileStore = useFileDataStore();
const props = defineProps({
  shareData: {
    type: Object,
    default: () => {
      return {
        expire_value: 1,
        expire_style: 'day',
      }
    }
  }
})
const handleSubmitShareText = ()=>{
  if (shareText.value === '') {
    alert('请输入您要分享的文本');
  } else {
    const formData = new FormData();
    formData.append('text', shareText.value);
    formData.append('expire_value', props.shareData.expireValue);
    formData.append('expire_style', props.shareData.expireStyle);
    request({
      'url': 'share/text/',
      'method': 'post',
      'data': formData,
    }).then((res: any) => {
      const data = res.detail;
      fileBoxStore.showFileBox = true;
      fileStore.addShareData({
        'name': '文本分享',
        'text': data.text,
        'code': data.code,
        'status': 'success',
        'percentage': 100,
        'size': shareText.value.length,
        'type': 'text',
        'uid': Date.now(),
      })
    });
  }
}
</script>

<template>
<div style="position: relative">
  <el-input
      placeholder="请输入您要寄出的文本"
      v-model="shareText"
      type="textarea"
      :rows="9"
      :input-style="{'border-radius':'20px','border':'1px dashed var(--el-border-color)','box-shadow':'none'}"
  >
  </el-input>
  <el-button @click="handleSubmitShareText" style="position: absolute;right: 0;top: 0;border-radius: 0 20px 0 20px;margin: 1px;background: rgba(255,255,255,0.2)" size="large">发送</el-button>
</div>
</template>

<style scoped lang="scss">

</style>