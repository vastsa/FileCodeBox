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
        <el-table-column prop="expired_count" :label="t('admin.fileView.expired_count')" />
        <el-table-column prop="size" :label="t('admin.fileView.size')">
          <template #default="scope">
            <span>{{ Math.round(scope.row.size/1024/1024*100)/100 }}MB</span>
          </template>
        </el-table-column>
        <el-table-column prop="expired_at" :label="t('admin.fileView.expired_at')">
          <template #default="scope">
            <span>{{ scope.row.expired_at ? scope.row.expired_at : '永久有效' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_path" :label="t('admin.fileView.file_path')" />
        <el-table-column>
          <template #header>
            {{ t('admin.fileView.action')}}
          </template>
          <template #default="scope">
            <el-button type="danger" size="small" @click="deleteFile(scope.row.id)">{{ t('admin.fileView.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination @size-change="updatePageSize" @current-change="updateCurrentPage" background layout="prev, pager, next" :page-size="params.size" :page-count="params.total/params.size" :total="params.total" />
  </main>
</template>
<script lang="ts" setup>
import { request } from "@/utils/request";
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
    ElMessage.success('删除成功');
    refreshData();
  });
};
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