<script setup lang="ts">
import { ref } from 'vue'
import { request } from "@/utils/request";
const shareText = ref('')
import { useFileDataStore } from "@/stores/fileData";
import { useFileBoxStore } from "@/stores/fileBox";
import { ElMessage } from "element-plus";

import { useI18n } from 'vue-i18n'
import { useConfigStore } from "@/stores/config";

const { t } = useI18n()
const {config} = useConfigStore();
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
    ElMessage.warning(t('send.prompt3'));
  } else if(config.openUpload === 0 && localStorage.getItem('adminPassword') === null){
    ElMessage.error(t('msg.uploadClose'));
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
        'name': t('send.textShare'),
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
      :placeholder="t('send.prompt3')"
      v-model="shareText"
      type="textarea"
      :rows="9"
      :input-style="{'border-radius':'20px','border':'1px dashed var(--el-border-color)','box-shadow':'none'}"
  >
  </el-input>
  <el-button @click="handleSubmitShareText" style="position: absolute;right: 0;bottom: 0;border-radius: 20px 0 20px 0;margin: 1px;background: rgba(255,255,255,0.2)" size="large">{{t('send.share')}}</el-button>
</div>
</template>

<style scoped lang="scss">

</style>