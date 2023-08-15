<template>
  <el-form>
    <el-form-item size="large" label="网站名称">
      <el-input v-model="config.name" />
    </el-form-item>
    <el-form-item size="large" label="网站描述">
      <el-input v-model="config.description" />
    </el-form-item>
    <el-form-item size="large" label="关键词" style="letter-spacing: 0.3rem">
      <el-input v-model="config.keywords" />
    </el-form-item>
    <el-form-item size="large" label="文件大小">
      <el-input type="number" v-model="config.uploadSize" />
      <template #append>Bit</template>
      <small>最大文件大小，单位:（bit),1mb=1 * 1024 * 1024</small>
    </el-form-item>
    <el-form-item size="large" label="开启上传">
      <el-select v-model="config.openUpload">
        <el-option label="开启游客上传" :value="1" />
        <el-option label="关闭游客上传" :value="0" />
      </el-select>
      <small style="margin-left: 0.4rem">关闭之后需要登录后台方可上传</small>
    </el-form-item>
    <el-form-item size="large" label="存储引擎">
      <el-select v-model="config.file_storage">
        <el-option label="本地存储" value="local" />
        <el-option label="S3存储" value="s3" />
      </el-select>
      <small style="margin-left: 0.4rem">更新后需要重启FileCodeBox</small>
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
    </div>
    <el-form-item size="large" label="上传限制">
        <span style="display: flex;height: 38px">
          <span style="margin-right: 0.4rem">每</span>
          <el-input type="number" v-model="config.uploadMinute" />
          <span style="width: 200px;margin-left: 0.4rem">分钟</span>
        </span>
        <span style="display: flex;height: 38px">
          <span style="width:3rem;margin-right: 0.4rem">上传</span>
          <el-input type="number" v-model="config.uploadCount" />
        <span style="width: 200px;margin-left: 0.4rem">个文件</span>
        </span>
    </el-form-item>
    <el-form-item size="large" label="错误限制">
        <span style="display: flex;height: 38px">
          <span style="margin-right: 0.4rem">每</span>
          <el-input type="number" v-model="config.errorMinute" />
          <span style="width: 200px;margin-left: 0.4rem">分钟</span>
        </span>
        <span style="display: flex;height: 38px">
          <span style="width:3rem;margin-right: 0.4rem">允许</span>
          <el-input type="number" v-model="config.errorCount" />
        <span style="width: 200px;margin-left: 0.4rem">次错误</span>
        </span>
    </el-form-item>
    <el-form-item>
      <el-button @click="submitSave" type="primary" style="margin: auto">保存</el-button>
    </el-form-item>
  </el-form>
</template>
<script lang="ts" setup>
import {ref} from "vue";
import { request } from "@/utils/request";
import { ElMessage } from "element-plus";

const config = ref({
  name: '',
  description: '',
  file_storage: '',
  keywords: '',
  openUpload: 1,
  uploadSize: 1,
  uploadMinute: 1,
  s3_access_key_id: '',
  s3_secret_access_key: '',
  s3_bucket_name: '',
  s3_endpoint_url: '',
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
      ElMessage.success('保存成功');
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
</style>