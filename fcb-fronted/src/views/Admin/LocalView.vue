<template>
  <div class="file-list">
    <el-empty style="width: 90vw;" v-if="localFiles.length===0" description="请在/opt/filecodebox/local目录上传您需要分享的文件" />
    <el-card v-for="file in localFiles" :key="file.name" class="file-card" shadow="hover">
      <div class="file-info">
        <div class="file-name">{{ file.file }}</div>
        <div class="file-date">{{ file.ctime }}</div>
        <div style="width: 100%;text-align: right">
          <el-button type="primary" style="margin-top: 1rem" @click="shareLocalFile(file)" plain>分享</el-button>
          <el-button type="danger" style="margin-top: 1rem" @click="deleteLocalFile(file)" plain>删除</el-button>
        </div>
      </div>
    </el-card>
    <el-dialog v-model="dialogFormVisible" width="500">
      <el-form :model="form">
        <el-form-item :label="t('admin.local.Name')" >
          <el-input v-model="form.name" readonly autocomplete="off" />
        </el-form-item>
        <el-form-item :label="t('admin.local.Expire')" >
          <el-input
              v-model="form.expireValue"
              style="width: 200px"
              :placeholder="t('send.pleaseInputExpireValue')"
          >
            <template #prepend>
              <el-select v-model="form.expireStyle" :placeholder="t('send.expireStyle')" style="width: 75px">
                <el-option v-for="item in config.expireStyle" :key="item" :label="t(`send.expireData.${item}`)" :value="item" />
              </el-select>
            </template>
            <template #append>
              <span v-if="form.expireStyle==='day'">{{t('send.expireValue.day')}}</span>
              <span v-else-if="form.expireStyle==='hour'">{{t('send.expireValue.hour')}}</span>
              <span v-else-if="form.expireStyle==='minute'">{{t('send.expireValue.minute')}}</span>
              <span v-else-if="form.expireStyle==='forever'">👌</span>
              <span v-else-if="form.expireStyle==='count'">{{t('send.expireValue.count')}}</span>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogFormVisible = false">{{ t('admin.local.Cancel') }}</el-button>
          <el-button type="primary" @click="toShareFile()">
            {{ t('admin.local.Confirm') }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import {ref, reactive} from 'vue';
import {request} from "@/utils/request";
import {ElMessage} from "element-plus";
import {useConfigStore} from "@/stores/config";
import {useI18n} from "vue-i18n";
const { t } = useI18n()

const { config } = useConfigStore();
const localFiles:any = ref([]);
const loadLocalFiles = ()=>{
  request({
    url: '/admin/local/lists',
    method: 'get',
  }).then((data:any) => {
    localFiles.value = data.detail;
  });
}
const dialogFormVisible = ref(false);

const form = reactive({
  name: '1',
  expireStyle: 'day',
  expireValue: 1,
})
loadLocalFiles()
const deleteLocalFile = (file: any) => {
  request({
    url: '/admin/local/delete',
    method: 'delete',
    data: {
      filename: file.file
    }
  }).then((data:any) => {
    ElMessage.success(data.detail);
    loadLocalFiles()
  });
};

const shareLocalFile = (file:any) => {
  form.name = file.file;
  dialogFormVisible.value = true;
};

const toShareFile=()=>{
  request({
    url: '/admin/local/share',
    method: 'post',
    data: {
      filename: form.name,
      expire_style: form.expireStyle,
      expire_value: form.expireValue
    }
  }).then((data:any) => {
    dialogFormVisible.value = false;
    ElMessage.success(
        {
          showClose: true,
          message: 'Code:' + data.detail.code,
          duration: 0
        }
    );
    loadLocalFiles()
  });
}
</script>

<style scoped>
.file-list {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  padding: 16px;
}

.file-card {
  align-items: center;
  justify-content: space-between;
  border-radius: 10px;
  transition: all 0.3s ease;
}

.file-card:hover {
  box-shadow: 0px 6px 15px rgba(0, 0, 0, 0.25);
}

.file-info {
  flex: 1;
}

.file-name {
  font-size: 14px;
  font-weight: bold;
  white-space: nowrap;
}

.file-date {
  font-size: 12px;
  color: #a0a0b2;
}


</style>
