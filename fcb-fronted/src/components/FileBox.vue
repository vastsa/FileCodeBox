<script setup lang="ts">
import { useFileDataStore } from "@/stores/fileData";
import { useFileBoxStore } from "@/stores/fileBox";
import hljs from 'highlight.js';
import mila from 'markdown-it-link-attributes';
import markdownIt from 'markdown-it';
import markdownItKatex from '@traptitech/markdown-it-katex';
import '@/assets/code/main.scss'
const fileStore = useFileDataStore();
const fileBoxStore = useFileBoxStore();
import QrcodeVue from "qrcode.vue";
import { useRoute } from "vue-router";
import { ref } from "vue";

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import { ElMessage } from "element-plus";
const openUrl = (url: string) => {
  if (url.startsWith('/')) {
    url = window.location.origin + url;
  }
  window.open(url);
};
const route = useRoute();

const copyText = (text: any, style = 0) => {
  ElMessage.success(t('fileBox.copySuccess'));
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
const nowText = ref('');
const showTextDetail = (text: any) => {
  showTextDetailVisible.value = true;
  nowText.value = text;
};

const showTextDetailVisible = ref(false);

const md = new markdownIt({
  html: false,
  linkify: true,
  highlight(code: any, language: any) {
    const validLang = Boolean(language && hljs.getLanguage(language));
    return `<pre class="code-block-wrapper"><code class="hljs code-block-body ${validLang}">${hljs.highlight(code, { language: language ?? '' }).value}</code></pre>`;
  }
});

md.use(mila, { attrs: { target: '_blank', rel: 'noopener' } });
md.use(markdownItKatex, { blockClass: 'katexmath-block rounded-md p-[10px]', errorColor: ' #cc0000' });
function renderMarkdown(message: string) {
  return md.render(message);
}

function getQrCodeUrl(code: string) {
  // 否是接收的文件，如果是则返回下载直链，否则拼接分享链接
  return code.toString().startsWith('/share/download') ? window.location.origin + code : window.location.origin + '/#/?code=' + code;
}
</script>

<template>
  <el-drawer :append-to-body="true" v-model="fileBoxStore.showFileBox" direction="btt" style="max-width: 1080px;margin: auto;"
             size="400">
    <template #header>
      <h4 v-if="route.name=='home'">{{t('fileBox.receiveFileBox')}}</h4>
      <h4 v-else>{{t('fileBox.sendFileBox')}}</h4>
    </template>
    <template #default>
      <div v-if="route.name=='home'" style="display: flex;flex-wrap: wrap;justify-content: center">
        <el-dialog
            append-to-body
            align-center
            :title="t('fileBox.textDetail')"
            width="70%"
            style="height: 70%;overflow-y: scroll"
            v-model="showTextDetailVisible"
        >
          <div style="max-width: 100%;overflow-y: scroll" v-html="renderMarkdown(nowText)"></div>
          <template #footer>
            <el-button type="success" @click="copyText(nowText);showTextDetailVisible = false">{{t('fileBox.copy')}}</el-button>
            <el-button type="primary" @click="showTextDetailVisible = false">{{ t('fileBox.close') }}</el-button>
          </template>
        </el-dialog>
        <el-card v-for="(value,index)  in fileStore.receiveData" :key="index" style="margin: 0.5rem">
          <template #header>
            <div style="display: flex;justify-content: space-between">
              <h4 style="width: 6rem;overflow: hidden;text-overflow: ellipsis;white-space: nowrap;">{{ value.name }}</h4>
              <el-button size="small" type="danger" @click="fileStore.deleteReceiveData(index)">{{ t('fileBox.delete') }}</el-button>
            </div>
          </template>
          <div style="width: 200px;">
            <div style="display: flex;justify-content: space-between">
              <!-- 下载二维码白色边框 -->
              <div v-if="value.name!=='文本分享'"
                   style="padding: 5px; background-color: white; border: 2px solid white; box-sizing: border-box; height: 114px;">
                <qrcode-vue :value="getQrCodeUrl(value.text)" :size="100"></qrcode-vue>
              </div>
              <div v-else style="width: 100px;height: 100px;flex-wrap: wrap;overflow-y:scroll ">{{value.text}}</div>
              <div style="display: flex;flex-direction: column;justify-content: space-around">
                <el-tag size="large" style="cursor: pointer" @click="copyText(value.code)">{{ value.code }}</el-tag>
                <el-tag v-if="value.name!=='文本分享'" size="large" type="success" style="cursor: pointer" @click="openUrl(value.text);">
                  {{ t('fileBox.download') }}
                </el-tag>
                <el-tag v-else size="large" type="success" style="cursor: pointer" @click="showTextDetail(value.text);">{{ t('fileBox.detail') }}</el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </div>
      <div v-else style="display: flex;flex-wrap: wrap;justify-content: center">
        <el-card v-for="(value,index) in fileStore.shareData" :key="index" style="margin: 0.5rem">
          <template #header>
            <div style="display: flex;justify-content: space-between">
              <h4 style="width: 6rem;overflow: hidden;text-overflow: ellipsis;white-space: nowrap;">{{ value.name }}</h4>
              <el-button size="small" type="danger" @click="fileStore.deleteShareData(index)">{{ t('fileBox.delete') }}</el-button>
            </div>
          </template>
          <div style="width: 200px;">
            <el-progress v-if="value.status!='success' && value.status!='fail'" striped :percentage="value.percentage" :text-inside="true"
                         :stroke-width="20"></el-progress>
            <div v-else style="display: flex;justify-content: space-between">
              <!-- 分享二维码白色边框 -->
              <div style="padding: 5px; background-color: white; border: 2px solid white; box-sizing: border-box; height: 114px;">
                <qrcode-vue :value="getQrCodeUrl(value.code)" :size="100"></qrcode-vue>
              </div>
              <div style="display: flex;flex-direction: column;justify-content: space-around">
                <el-tag size="large" style="cursor: pointer" @click="copyText(value.code)">{{ value.code }}</el-tag>
                <el-tag size="large" type="success" style="cursor: pointer" @click="copyText(value.code,1);">{{ t('fileBox.copyLink') }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </template>
  </el-drawer>
</template>