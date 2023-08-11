<script setup lang="ts">
import { Upload, TakeawayBox } from '@element-plus/icons-vue';
import { ref } from 'vue'
import { useRouter } from "vue-router";
import CardTools from "@/components/CardTools.vue";
import { useFileBoxStore } from "@/stores/fileBox";
const fileBoxStore = useFileBoxStore();
const router = useRouter()
const code = ref('')
const listenInput = (num: number) => {
  console.log('listenInput',num)
};
</script>

<template>
    <main>
      <el-card class="card" style="padding-bottom: 1rem">
        <CardTools/>
        <el-row style="text-align: center">
          <el-col :span="24">
            <el-input v-model="code" class="code-input" round autofocus clearable maxlength="5" placeholder="请输入五位取件码"/>
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