<div align="center">

<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/static/banners/img_1.png" alt="FileCodeBox Logo">

<p><em>匿名口令分享文本和文件，像拿快递一样取文件</em></p>

[![GitHub stars](https://img.shields.io/github/stars/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/network)
[![GitHub issues](https://img.shields.io/github/issues/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/issues)
[![GitHub license](https://img.shields.io/github/license/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/blob/master/LICENSE)
[![QQ Group](https://img.shields.io/badge/QQ%20Group-739673698-blue.svg)](https://qm.qq.com/q/PemPzhdEIM)
[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.68+-green.svg)](https://fastapi.tiangolo.com)
[![Vue Version](https://img.shields.io/badge/Vue.js-3.x-brightgreen.svg)](https://v3.vuejs.org)
</div>


## 🚀 更新计划
- [ ] 切片上传，同文件秒传，断点续传
- [ ] 用户登录重构
- [x] webdav存储
- [x] 存储支持自定义路径
- [x] s3优化，不修改昵称为uuid，新建目录

## 📝 项目简介

FileCodeBox 是一个基于 FastAPI + Vue3 开发的轻量级文件分享工具。它允许用户通过简单的方式分享文本和文件，接收者只需要一个提取码就可以取得文件，就像从快递柜取出快递一样简单。

## 🎯 应用场景

<table>
<tr>
<td align="center">
<h4>📁 临时文件分享</h4>
快速分享单个文件，无需注册登录
</td>
<td align="center">
<h4>📝 文本快速分享</h4>
分享代码片段、文本内容等
</td>
<td align="center">
<h4>🕶️ 匿名文件传输</h4>
保护隐私的文件传输方式
</td>
</tr>
<tr>
<td align="center">
<h4>💾 临时文件存储</h4>
支持设置过期时间的文件存储
</td>
<td align="center">
<h4>🔄 跨平台传输</h4>
在不同设备间快速传输文件
</td>
<td align="center">
<h4>🌐 小型分享服务</h4>
搭建私有的文件分享服务
</td>
</tr>
</table>

## ✨ 核心特性

<table>
<tr>
<td align="center">
<h4>🚀 轻量简洁</h4>
基于 FastAPI + SQLite3 + Vue3 + ElementUI，部署简单，性能出色
</td>
<td align="center">
<h4>📤 便捷上传</h4>
支持复制粘贴、拖拽上传，操作简单直观
</td>
<td align="center">
<h4>📦 多种类型</h4>
支持文本和各类文件的分享
</td>
</tr>
<tr>
<td align="center">
<h4>🔒 安全机制</h4>

- IP 限制上传次数
- 错误次数限制
- 文件过期机制
</td>
<td align="center">
<h4>🎫 提取码分享</h4>
随机提取码，可自定义次数及有效期
</td>
<td align="center">
<h4>🌍 多语言支持</h4>
支持中文简体、繁体及英文
</td>
</tr>
<tr>
<td align="center">
<h4>🎭 匿名分享</h4>
无需注册登录，保护隐私
</td>
<td align="center">
<h4>🛠 管理面板</h4>
文件管理和系统配置
</td>
<td align="center">
<h4>🐳 容器部署</h4>
支持 Docker 一键部署
</td>
</tr>
<tr>
<td align="center">
<h4>💾 存储扩展</h4>
支持本地存储、S3 协议、OneDrive 等
</td>
<td align="center">
<h4>📱 响应式设计</h4>
支持移动端访问
</td>
<td align="center">
<h4>💻 终端支持</h4>
支持命令行下载
</td>
</tr>
</table>

## 🚀 快速开始

### Docker 部署

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:beta
```

### 手动部署

1. 克隆项目
```bash
git clone https://github.com/vastsa/FileCodeBox.git
```

2. 安装依赖
```bash
cd FileCodeBox
pip install -r requirements.txt
```

3. 启动服务
```bash
python main.py
```

## 📖 使用说明

### 分享文件
1. 打开网页，点击"分享文件"
2. 选择或拖拽文件
3. 设置过期时间和次数
4. 获取提取码

### 获取文件
1. 打开网页，输入提取码
2. 点击获取
3. 下载文件或查看文本

### 管理面板
1. 访问 `/admin`
2. 输入管理员密码
3. 管理文件和配置

## 🛠 开发指南

### 项目结构
```
FileCodeBox/
├── apps/           # 应用代码
│   ├── admin/     # 管理后台
│   └── base/      # 基础功能
├── core/          # 核心功能
├── data/          # 数据目录
└── fcb-fronted/   # 前端代码
```

### 开发环境
- Python 3.8+
- Node.js 14+
- Vue 3
- FastAPI

### 本地开发
1. 后端开发
```bash
python main.py
```

2. 前端开发
```bash
cd fcb-fronted
npm install
npm run dev
```

## 🤝 贡献指南

1. Fork 本项目
2. 创建新分支 `git checkout -b feature/xxx`
3. 提交更改 `git commit -m 'Add xxx'`
4. 推送到分支 `git push origin feature/xxx`
5. 提交 Pull Request

## ❓ 常见问题

### Q: 如何修改上传大小限制？
A: 在管理面板中修改配置项 `uploadSize`

### Q: 如何配置存储引擎？
A: 在管理面板中选择存储引擎并配置相应参数

### Q: 如何备份数据？
A: 备份 `data` 目录即可

更多问题请访问 [Wiki](https://github.com/vastsa/FileCodeBox/wiki/常见问题)

## 📊 项目统计

<div align="center">
<a href="https://hellogithub.com/repository/75ad7ffedd404a6485b4d621ec5b47e6" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=75ad7ffedd404a6485b4d621ec5b47e6&claim_uid=beSz6INEkCM4mDH" alt="Featured｜HelloGitHub" style="width: 200px; height: 45px;" width="200" height="45" /></a>

![Repobeats](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg)

[![Star History](https://api.star-history.com/svg?repos=vastsa/FileCodeBox&type=Date)](https://star-history.com/#vastsa/FileCodeBox&Date)
</div>

## 📜 免责声明

本项目开源仅供学习使用，不得用于任何违法用途，否则后果自负，与作者无关。使用时请保留项目地址和版权信息。
