<script setup lang="ts">
import { useDark, useToggle } from '@vueuse/core'
import { useRoute, useRouter } from "vue-router";
const router = useRouter()
const route = useRoute()
const isDark = useDark()
const toggleDark = useToggle(isDark)
import { Moon, Sunny, Upload, Back, TakeawayBox } from "@element-plus/icons-vue";
import FileBox from "@/components/FileBox.vue";
import { useFileBoxStore } from "@/stores/fileBox";
const fileBoxStore = useFileBoxStore();
</script>

<template>
  <div class="tools">
    <div class="circle">
      <el-icon size="17" color="#212121" class="red box" @click="router.push({'name':route.name=='home'?'send':'home'})">
        <Back v-if="route.name=='send'"></Back>
        <Upload v-else></Upload>
      </el-icon>
    </div>
    <div class="circle">
      <el-icon size="17" color="#212121" class="yellow box" @click="toggleDark(!isDark)">
        <Moon v-if="isDark"></Moon>
        <Sunny v-else></Sunny>
      </el-icon>
    </div>
    <div class="circle">
      <el-icon size="17" color="#212121" class="green box" @click="fileBoxStore.showFileBox=true">
        <TakeawayBox></TakeawayBox>
      </el-icon>
    </div>
    <file-box></file-box>
  </div>
</template>

<style scoped lang="scss">

</style>