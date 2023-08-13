<script setup lang="ts">
import { Upload, TakeawayBox } from '@element-plus/icons-vue';
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from "vue-router";
import CardTools from "@/components/CardTools.vue";
import { useFileBoxStore } from "@/stores/fileBox";
import { useFileDataStore } from "@/stores/fileData";

import { request } from "@/utils/request";
const fileBoxStore = useFileBoxStore();
const fileStore = useFileDataStore();
const router = useRouter()
const route = useRoute()
const code = ref('')
const input_status = reactive({
  'readonly': false,
  'loading': false,
})
onMounted(() => {
  const query_code = route.query.code as string;
  if (query_code) {
    code.value = query_code
  }
})
watch(code, (newVal) => {
  if (newVal.length === 5) {
    input_status.readonly = true;
    input_status.loading = true;
    request({
      'url': '/share/select',
      'method': 'POST',
      'data': {
        'code': newVal
      }
    }).then((res: any) => {
      input_status.readonly = false;
      input_status.loading = false;
      code.value = '';
      if (res.data.code === 200) {
        fileBoxStore.showFileBox = true;
        let flag = true;
        fileStore.receiveData.forEach((file: any) => {
          if (file.code === res.data.data.code) {
            flag = false;
            return;
          }
        });
        if (flag) {
          fileStore.addReceiveData(res.data.data);
        }
      } else {
        alert(res.data.msg||'未知错误')
      }
    });
  }
});
const listenInput = (num: number) => {
  if (code.value.length < 5) {
    code.value += num
  }
};

</script>

<template>
    <main>
      <el-card class="card" style="padding-bottom: 1rem">
        <CardTools/>
        <el-row style="text-align: center">
          <el-col :span="24">
            <el-input :readonly="input_status.readonly" v-loading="input_status.loading" v-model="code" class="code-input" round autofocus clearable maxlength="5" placeholder="请输入五位取件码"/>
          </el-col>
          <el-col :span=8 v-for="i in 9" :key="i">
            <el-button class="key-button" round @click="listenInput(i)">{{ i }}</el-button>
          </el-col>
          <el-col :span=8>
            <el-button @click="router.push({'name':'send'})"  class="key-button" :icon="Upload" round>
            </el-button>
          </el-col>
          <el-col :span=8>
            <el-button class="key-button" round @click="listenInput(0)">0</el-button>
          </el-col>
          <el-col :span=8>
            <el-button class="key-button" round :icon="TakeawayBox" @click="fileBoxStore.showFileBox=true">
            </el-button>
          </el-col>
        </el-row>
      </el-card>
    </main>
</template>
<style lang='scss'>
  .key-button{
    width: 6rem;
    height: 6rem;
    margin: 0.2rem;
    font-size: 2rem;
    font-weight: bold;
    text-align: center;
  }

  .code-input {
    height: 100px;
    font-size: 30px;
    font-weight: bold;
    margin: 1rem 0;
    .el-input__wrapper{
      border-radius: 20px !important;
    }
  }
</style>