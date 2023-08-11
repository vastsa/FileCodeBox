<script setup lang="ts">
import { useFileDataStore } from "@/stores/fileData";
import { useFileBoxStore } from "@/stores/fileBox";

const fileStore = useFileDataStore();
const fileBoxStore = useFileBoxStore();
import QrcodeVue from "qrcode.vue";
import { useRoute } from "vue-router";

const copyText = (text: any, style = 0) => {
  if (style === 1) {
    text = window.location.origin + '/#/?code=' + text;
  }
  const temp: any = document.createElement('textarea');
  temp.value = text;
  document.body.appendChild(temp);
  temp.select();
  if (document.execCommand('copy')) {
    document.execCommand('copy');
  }
  document.body.removeChild(temp);
};
const route = useRoute();
</script>

<template>
  <el-drawer append-to-body v-model="fileBoxStore.showFileBox" direction="btt" style="max-width: 1080px;margin: auto;"
             size="400">
    <template #header>
      <h4>文件箱</h4>
    </template>
    <template #default>
      <div v-if="route.name=='home'">
        <el-card v-for="i in fileStore.receiveData" :key="i">
          {{ i }}
          <template #header>
            <el-button type="danger" @click="fileStore.deleteReceiveData(i)">删除</el-button>
          </template>
        </el-card>
      </div>
      <div v-else style="display: flex;flex-wrap: wrap;justify-content: center">
        <el-card v-for="(value,index) in fileStore.shareData" :key="index" style="margin: 0.5rem">
          <template #header>
            <div style="display: flex;justify-content: space-between">
              <h4 style="width: 6rem;overflow: hidden;text-overflow: ellipsis;white-space: nowrap;">{{ value.name }}</h4>
              <el-button size="small" type="danger" @click="fileStore.deleteShareData(index)">删除</el-button>
            </div>
          </template>
          <div style="width: 200px;">
            <el-progress v-if="value.status!='success'" striped :percentage="value.percentage" :text-inside="true"
                         :stroke-width="20"></el-progress>
            <div style="display: flex;justify-content: space-between">
              <qrcode-vue :value="value.text" :size="100"></qrcode-vue>
              <div style="display: flex;flex-direction: column;justify-content: space-around">
                <el-tag size="large" style="cursor: pointer" @click="copyText(value.code)">{{ value.code }}</el-tag>
                <el-tag size="large" type="success" style="cursor: pointer" @click="copyText(value.code,1);">复制链接
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </template>
  </el-drawer>
</template>