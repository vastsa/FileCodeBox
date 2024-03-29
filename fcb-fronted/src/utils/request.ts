// @ts-ignore
import axios from "axios";
import { ElMessage } from "element-plus";
const instance = axios.create({
  baseURL: import.meta.env.DEV ? "http://localhost:12345" : "/",
  timeout: 6000000,
});
instance.interceptors.request.use(
  (config: any) => {
    config.headers= {
      'Authorization': localStorage.getItem('adminPassword') || '',
    }
    return config;
  });
instance.interceptors.response.use(
  (response:any) => {
    if (response.status === 200 && response.config.url === '/admin/file/download') {
      return response;
    }
    if (response.data.code === 200) {
      return response.data;
    } else {
      ElMessage.error(response.data.detail);
      return Promise.reject(response.data);
    }
  }, (error:any) => {
    ElMessage.error(error.response.data.detail);
    return Promise.reject(error);
  });

export const request = instance;
