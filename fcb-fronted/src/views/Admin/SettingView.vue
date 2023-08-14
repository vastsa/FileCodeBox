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
    <el-form-item size="large" label="开启上传">
      <el-select v-model="config.openUpload">
        <el-option label="开启游客上传" value="1" />
        <el-option label="关闭游客上传" value="0" />
      </el-select>
    </el-form-item>
    <el-form-item size="large" label="文件大小">
      <el-input v-model="config.uploadSize" />
      <template #append>Bit</template>
      <small>最大文件大小，单位:（bit),1mb=1 * 1024 * 1024</small>
    </el-form-item>
    <el-form-item size="large" label="上传限制">
        <span style="display: flex;height: 38px">
          <span style="margin-right: 0.4rem">每</span>
          <el-input v-model="config.uploadMinute" />
          <span style="width: 200px;margin-left: 0.4rem">分钟</span>
        </span>
        <span style="display: flex;height: 38px">
          <span style="width:3rem;margin-right: 0.4rem">上传</span>
          <el-input v-model="config.uploadCount" />
        <span style="width: 200px;margin-left: 0.4rem">个文件</span>
        </span>
    </el-form-item>
    <el-form-item size="large" label="错误限制">
        <span style="display: flex;height: 38px">
          <span style="margin-right: 0.4rem">每</span>
          <el-input v-model="config.uploadMinute" />
          <span style="width: 200px;margin-left: 0.4rem">分钟</span>
        </span>
        <span style="display: flex;height: 38px">
          <span style="width:3rem;margin-right: 0.4rem">允许</span>
          <el-input v-model="config.uploadCount" />
        <span style="width: 200px;margin-left: 0.4rem">次错误</span>
        </span>
    </el-form-item>
    <el-form-item>
      <el-button type="primary" style="margin: auto">保存</el-button>
    </el-form-item>
  </el-form>
</template>
<script lang="ts" setup>
import {ref} from "vue";

const config = ref({
  name: '',
  description: '',
  keywords: '',
  openUpload: '1',
  uploadSize: '1',
  uploadMinute: '1',
  uploadCount: '1',
});
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