// @ts-ignore
import axios from "axios";

const instance = axios.create({
  baseURL: "http://localhost:12345",
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
      alert(response.data.detail);
      return Promise.reject(response.data);
    }
  }, (error:any) => {
    alert(error.response.data.detail);
    return Promise.reject(error);
  });

export const request = instance;
