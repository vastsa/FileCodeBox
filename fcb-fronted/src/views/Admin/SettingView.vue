<template>
  <el-form>
    <el-form-item size="large" :label="t('admin.settings.name')">
      <el-input v-model="config.name" />
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.description')">
      <el-input v-model="config.description" />
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.keywords')" style="letter-spacing: 0.3rem">
      <el-input v-model="config.keywords" />
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.background')">
      <el-input v-model="config.background" />
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.admin_token')">
      <el-input type="password" v-model="config.admin_token" />
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.uploadSize')">
      <el-input type="number" v-model="config.uploadSize" />
      <template #append>Bytes</template>
      <small>{{ t('admin.settings.uploadSizeNote') }}</small>
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.openUpload.title')">
      <el-select v-model="config.openUpload">
        <el-option :label="t('admin.settings.openUpload.open')" :value="1" />
        <el-option :label="t('admin.settings.openUpload.close')" :value="0" />
      </el-select>
      <small style="margin-left: 0.4rem">{{ t('admin.settings.openUpload.note') }}</small>
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.file_storage.title')">
      <el-select v-model="config.file_storage">
        <el-option :label="t('admin.settings.file_storage.local')" value="local" />
        <el-option :label="t('admin.settings.file_storage.s3')" value="s3" />
      </el-select>
      <small style="margin-left: 0.4rem">{{ t('admin.settings.file_storage.note') }}</small>
    </el-form-item>
    <div v-if="config.file_storage==='s3'">
      <el-form-item size="large" label="S3 AccessKeyId">
        <el-input v-model="config.s3_access_key_id" />
      </el-form-item>
      <el-form-item size="large" label="S3 SecretAccessKey">
        <el-input v-model="config.s3_secret_access_key" />
      </el-form-item>
      <el-form-item size="large" label="S3 BucketName">
        <el-input v-model="config.s3_bucket_name" />
      </el-form-item>
      <el-form-item size="large" label="S3 EndpointUrl">
        <el-input v-model="config.s3_endpoint_url" />
      </el-form-item>
	  <el-form-item size="large" label="S3 hostname">
        <el-input v-model="config.s3_hostname" />
      </el-form-item>
	  <el-form-item size="large" label="S3 region name">
        <el-input v-model="config.s3_region_name" />
      </el-form-item>
	  <el-form-item size="large" label="S3 Signature Version">
        <el-input v-model="config.s3_signature_version" />
      </el-form-item>
      <el-form-item size="large" label="Aws Session Token">
        <el-input v-model="config.aws_session_token" />
      </el-form-item>
    </div>
    <el-form-item size="large" :label="t('admin.settings.uploadlimit')">
        <span style="display: flex;height: 38px">
          <span style="margin-right: 0.4rem">{{ t('admin.settings.mei') }}</span>
          <el-input type="number" v-model="config.uploadMinute" />
          <span style="width: 200px;margin-left: 0.4rem">{{ t('admin.settings.minute') }}</span>
        </span>
        <span style="display: flex;height: 38px">
          <span style="width:3rem;margin-right: 0.4rem">{{ t('admin.settings.upload') }}</span>
          <el-input type="number" v-model="config.uploadCount" />
        <span style="width: 200px;margin-left: 0.4rem">{{ t('admin.settings.files') }}</span>
        </span>
    </el-form-item>
    <el-form-item size="large" :label="t('admin.settings.errorlimit')">
        <span style="display: flex;height: 38px">
          <span style="margin-right: 0.4rem">{{ t('admin.settings.mei') }}</span>
          <el-input type="number" v-model="config.errorMinute" />
          <span style="width: 200px;margin-left: 0.4rem">{{ t('admin.settings.minute') }}</span>
        </span>
        <span style="display: flex;height: 38px">
          <span style="width:3rem;margin-right: 0.4rem">{{ t('admin.settings.allow') }}</span>
          <el-input type="number" v-model="config.errorCount" />
        <span style="width: 200px;margin-left: 0.4rem">{{ t('admin.settings.errors') }}</span>
        </span>
    </el-form-item>
    <el-form-item>
      <el-button @click="submitSave" type="primary" style="margin: auto">{{ t('admin.settings.save') }}</el-button>
    </el-form-item>
  </el-form>
</template>
<script lang="ts" setup>
import {ref} from "vue";
import { request } from "@/utils/request";
import { ElMessage } from "element-plus";

import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const config = ref({
  name: '',
  description: '',
  file_storage: '',
  admin_token: '',
  keywords: '',
  openUpload: 1,
  uploadSize: 1,
  uploadMinute: 1,
  s3_access_key_id: '',
  background: '',
  s3_secret_access_key: '',
  aws_session_token: '',
  s3_signature_version: '',
  s3_region_name: '',
  s3_bucket_name: '',
  s3_endpoint_url: '',
  s3_hostname: '',
  uploadCount: 1,
  errorMinute: 1,
  errorCount: 1,
});
const refreshData = ()=>{
  request({
    url: '/admin/config/get',
    method: 'get'
  }).then((res: any) => {
    config.value = res.detail;
  });
}
refreshData();
const submitSave = () => {
  request({
    url: '/admin/config/update',
    method: 'patch',
    data: config.value
  }).then((res: any) => {
    if (res.code == 200) {
      ElMessage.success(t('admin.settings.saveSuccess'));
    } else {
      ElMessage.error(res.message);
    }
  });
};
</script>
<style lang="scss">

.left-menu {
  margin-bottom: 1rem;
  cursor: pointer;
  text-align: center;
  font-weight: bold;
  font-size: 1rem;
  letter-spacing: 0.4rem;
}
small{
  color: #909399;
  margin-left: 0.4rem;
}
</style>