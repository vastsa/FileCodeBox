// @ts-ignore
import axios from "axios";
import { ElMessage } from "element-plus";

const instance = axios.create({
  baseURL: import.meta.env.DEV ? "http://localhost:12345" : "/",
  timeout: 6000000,
  headers:{
    'Authorization':localStorage.getItem('auth')
  }
});
// 对响应进行拦截
instance.interceptors.response.use(
  (response:any) => {
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
