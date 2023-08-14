<template>
  <main>
      <el-table stripe :data="tableData" style="width: 100%">
        <el-table-column prop="code" label="取件码" />
        <el-table-column prop="prefix" label="文件前缀" />
        <el-table-column prop="suffix" label="后缀" />
        <el-table-column prop="text" label="文本">
          <template #default="scope">
            <span style="width: 6rem;overflow: hidden;text-overflow: ellipsis;white-space: nowrap;">{{ scope.row.text }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="used_count" label="已用次数" />
        <el-table-column prop="expired_count" label="可用次数" />
        <el-table-column prop="file_path" label="文件路径" />
        <el-table-column>
          <template #header>
            操作
          </template>
          <template #default="scope">
            <el-button type="danger" size="small" @click="deleteFile(scope.row.id)">删除</el-button>
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