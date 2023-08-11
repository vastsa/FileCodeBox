// @ts-ignore
import axios from "axios";

const instance = axios.create({
  baseURL: "",
  timeout: 6000000,
  headers:{
    'Authorization':localStorage.getItem('auth')
  }
});

const Request = axios.create({
  baseURL: "http://localhost:8000",
  timeout: 6000000,
});

export const request = Request;
export const http = instance;
