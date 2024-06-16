<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { request } from "@/utils/request";
import { useFileDataStore } from "@/stores/fileData";
import { useFileBoxStore } from "@/stores/fileBox";
import { useI18n } from 'vue-i18n'
import { useConfigStore } from "@/stores/config";
import { ElMessage } from "element-plus";

const { config } = useConfigStore();
const { t } = useI18n()
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

const fileList: any = ref([])
const uploadBox: any = ref(null)
const handleOnChangeFileList = (file: any) => {
  fileStore.addShareData({
    'name': file.name,
    'text': '',
    'status': file.status,
    'percentage': 0,
    'size': file.size,
    'type': file.raw.type,
    'uid': file.uid,
  });
};

const handleHttpRequest = (options: any) => {
  fileBoxStore.showFileBox = true;
  const formData = new FormData();
  if (config.openUpload === 0 && localStorage.getItem('adminPassword') === null) {
    fileStore.shareData.forEach((file: any) => {
      if (file.uid === options.file.uid) {
        ElMessage.error(t('msg.uploadClose'));
        file.status = 'fail';
        file.code = t('msg.fileUploadFail');
        fileStore.save();
      }
    });
    return;
  }
  if (options.file.size > config.uploadSize) {
    fileStore.shareData.forEach((file: any) => {
      if (file.uid === options.file.uid) {
        ElMessage.error(t('msg.fileOverSize'));
        file.status = 'fail';
        file.code = t('msg.fileOverSize');
        fileStore.save();
      }
    });
    return;
  }
  formData.append('file', options.file);
  formData.append('expire_value', props.shareData.expireValue);
  formData.append('expire_style', props.shareData.expireStyle);
  request(
      {
        url: "share/file/",
        method: "post",
        data: formData,
        onUploadProgress: (event: any) => {
          const percentage = Math.round((event.loaded * 100) / event.total) || 0;
          fileStore.shareData.forEach((file: any) => {
            if (file.uid === options.file.uid) {
              file.percentage = percentage;
              fileStore.save();
            }
          });
        }
      }
  ).then((res: any) => {
    const data = res.detail;
    fileStore.shareData.forEach((file: any) => {
      if (file.uid === options.file.uid) {
        file.status = 'success';
        file.text = data.text;
        file.code = data.code;
        ElMessage.success(t('msg.fileUploadSuccess'));
        fileStore.save();
      }
    });
  }).catch(() => {
    fileStore.shareData.forEach((file: any) => {
      if (file.uid === options.file.uid) {
        file.status = 'fail';
        file.code = t('msg.fileUploadFail');
        ElMessage.error(t('msg.fileUploadFail'));
        fileStore.save();
      }
    });
  });
};
function pasteLister(event: any) {
    const items = event.clipboardData && event.clipboardData.items;
    if (items && items.length) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'string') {
          if (items[i].type.match(/^text\/plain/)) {
            items[i].getAsString(function(str:any) {
              console.log(str);
            });
          }
        } else {
          const file: any = items[i].getAsFile();
          if (file) {
            const uid = Date.now();
            file.uid = uid;
            fileStore.addShareData({
              'name': file.name,
              'text': '',
              'status': 'ready',
              'percentage': 0,
              'size': file.size,
              'type': file.type,
              'uid': uid,
            });
            handleHttpRequest({
              file: file,
            })
        }
      }
    }
  }
}
onUnmounted(()=>{
  // 清除剪切板事件
  document.removeEventListener('paste', pasteLister);
})
onMounted(()=>{
  document.addEventListener('paste', pasteLister);
})
</script>

<template>
  <div>
    <el-upload
        class="upload-demo"
        drag
        multiple
        :show-file-list="false"
        ref="uploadBox"
        v-model:file-list="fileList"
        :on-change="handleOnChangeFileList"
        :http-request="handleHttpRequest"
    >
      <el-icon class="el-icon--upload">
        <upload-filled/>
      </el-icon>
      <div class="el-upload__text">
        {{t('send.prompt1')}}<em>{{t('send.clickUpload')}}</em>
      </div>
      <div class="el-upload__text" style="font-size: 10px;">{{t('send.prompt2')}}</div>
      <template #tip>
        <div class="el-upload__tip">
        </div>
      </template>
    </el-upload>
  </div>
</template>

<style lang="scss">
.el-upload {
  border-radius: 20px;
}

.el-upload-dragger {
  box-shadow: 3px 3px 0 0 rgba(0, 0, 0, 0.2);
  border-radius: 20px;
}
</style>