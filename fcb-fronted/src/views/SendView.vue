<script setup lang="ts">
import { ref } from 'vue'
import CardTools from "@/components/CardTools.vue";
import UploadFile from "@/components/UploadFile.vue";
import UploadText from "@/components/UploadText.vue";
const shareData = ref({
  expireValue: 1,
  expireStyle: 'day',
  targetType: 'file',
})
</script>

<template>
  <main>
    <el-card class="card" style="padding: 1rem;position: relative"  :body-style="{ padding: '0px 0px 20px 0px' }">
      <card-tools/>
      <div style="display: flex;margin-top: 1rem">
        <div>
          <el-input
              v-model="shareData.expireValue"
              style="width: 200px"
              placeholder="请输入值"
          >
            <template #prepend>
              <el-select v-model="shareData.expireStyle" placeholder="过期方式" style="width: 75px">
                <el-option label="天数" value="day" />
                <el-option label="小时" value="hour" />
                <el-option label="分钟" value="minute" />
                <el-option label="永久" value="forever" />
                <el-option label="次数" value="count" />
              </el-select>
            </template>
            <template #append>
              <span v-if="shareData.expireStyle=='day'">天</span>
              <span v-else-if="shareData.expireStyle=='hour'">时</span>
              <span v-else-if="shareData.expireStyle=='minute'">分</span>
              <span v-else-if="shareData.expireStyle=='forever'">👌</span>
              <span v-else-if="shareData.expireStyle=='count'">次</span>
            </template>
          </el-input>
        </div>
        <el-radio-group v-model="shareData.targetType" style="margin-left: 1rem;">
          <el-radio label="file">文件</el-radio>
          <el-radio label="text">文本</el-radio>
        </el-radio-group>
      </div>
      <div style="margin-top: 1rem">
        <upload-file :shareData="shareData" v-if="shareData.targetType=='file'"/>
        <upload-text :shareData="shareData" v-else-if="shareData.targetType=='text'"/>
      </div>
    </el-card>
  </main>
</template>