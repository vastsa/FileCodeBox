<template>
  <main>
      <el-table size="large" stripe :data="tableData" style="width: 100%">
        <el-table-column prop="code" :label="t('admin.fileView.code')" />
        <el-table-column prop="prefix" :label="t('admin.fileView.prefix')" />
        <el-table-column prop="suffix" :label="t('admin.fileView.suffix')" />
        <el-table-column prop="text" :label="t('admin.fileView.text')">
          <template #default="scope">
            <span style="width: 6rem;overflow: hidden;text-overflow: ellipsis;white-space: nowrap;">{{ scope.row.text }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="used_count" :label="t('admin.fileView.used_count')" />
        <el-table-column prop="expired_count" :label="t('admin.fileView.expired_count')">
          <template #default="scope">
            <span>{{ scope.row.expired_count > -1 ? scope.row.expired_count : t('admin.fileView.unlimited_count') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="size" :label="t('admin.fileView.size')">
          <template #default="scope">
            <span>{{ Math.round(scope.row.size/1024/1024*100)/100 }}MB</span>
          </template>
        </el-table-column>
        <el-table-column prop="expired_at" :label="t('admin.fileView.expired_at')">
          <template #default="scope">
            <span>{{ scope.row.expired_at ? formatTimestamp(scope.row.expired_at) : t('admin.fileView.forever') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_path" :label="t('admin.fileView.file_path')" />
        <el-table-column>
          <template #header>
            {{ t('admin.fileView.action')}}
          </template>
          <template #default="scope">
            <el-button type="danger" size="small" @click="deleteFile(scope.row.id)">{{ t('admin.fileView.delete') }}</el-button>
            <el-button type="success" size="small" @click="downloadFile(scope.row.id)" v-if="scope.row.file_path">{{ t('admin.fileView.download') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination @size-change="updatePageSize" @current-change="updateCurrentPage" background layout="prev, pager, next" :page-size="params.size" :page-count="Math.round(params.total/params.size)" :total="params.total" />
  </main>
</template>
<script lang="ts" setup>
import { request } from "@/utils/request";
import { formatTimestamp } from "@/utils/timestamp-format"
import { ref } from "vue";
import { ElMessage } from "element-plus";
const tableData = ref([]);
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const params = ref({
  page: 1,
  size: 10,
  total: 0,
});
const updateCurrentPage = (currentPage: number) => {
  params.value.page = currentPage;
  refreshData();
};
const deleteFile = (id: number) => {
  request({
    url: '/admin/file/delete',
    method: 'delete',
    data: {
      id,
    },
  }).then(() => {
    ElMessage.success(t('admin.fileView.delete_success'));
    refreshData();
  });
};
const downloadFile = (id: number) => {

  request({
    url: '/admin/file/download',
    method: 'get',
    params: {
      id,
    },
    responseType: 'blob'
  }).then((response: any) => {
    const contentDisposition = response.headers['content-disposition'];
    let filename = 'file';
    // 使用正则表达式来提取文件名
    const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    if (filenameMatch != null && filenameMatch[1]) {
      // 去除文件名周围的引号
      filename = filenameMatch[1].replace(/['"]/g, '');
    }
    // @ts-ignore
    if (window.showSaveFilePicker)
      saveFileByWebApi(response.data, filename).catch(() => {
        // ElMessage.error('文件保存函数不支持您的浏览器');
        saveFileByElementA(response.data, filename).catch(() => {
          ElMessage.error(t('admin.fileView.download_fail'));
        })
      })
    else
      saveFileByElementA(response.data, filename).catch(() => {
        ElMessage.error(t('admin.fileView.download_fail'));
      })
  });
};

async function saveFileByElementA(fileBlob: Blob, filename: string) {
  const downloadUrl = window.URL.createObjectURL(fileBlob);
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.download = filename; // 设置下载文件名
  document.body.appendChild(link);
  link.click();
  // 清理并释放URL对象
  window.URL.revokeObjectURL(downloadUrl);
  document.body.removeChild(link);
}

async function saveFileByWebApi(fileBlob: Blob, filename: string) {
  // 创建一个新句柄。
  // @ts-ignore
  const newHandle = await window.showSaveFilePicker({
    suggestedName: filename,
  });
  // 创建一个 FileSystemWritableFileStream 用于写入。
  const writableStream = await newHandle.createWritable();
  // 写入我们的文件。
  await writableStream.write(fileBlob);
  // 关闭文件并将内容写入磁盘。
  await writableStream.close();
}


const updatePageSize=(pageSize: number) => {
  params.value.size = pageSize;
  refreshData();
};
const refreshData=() => {
  request({
    url: '/admin/file/list',
    method: 'get',
    params: params.value,
  }).then((res:any) => {
    tableData.value = res.detail.data;
    params.value.total = res.detail.total;
  });
}
refreshData();
</script>