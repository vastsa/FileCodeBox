# 快速开始

## 简介

FileCodeBox 是一个简单高效的文件分享工具，支持文件临时中转、分享和管理。本指南将帮助您快速部署和使用 FileCodeBox。

## 特性

- 🚀 快速部署：支持 Docker 一键部署
- 🔒 安全可靠：文件访问需要提取码
- ⏱️ 时效控制：支持设置文件有效期
- 📊 下载限制：可限制文件下载次数
- 🖼️ 文件预览：支持图片、视频、音频等多种格式预览
- 📱 响应式设计：完美适配移动端和桌面端

## 部署方式

### Docker 部署（推荐）

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


## 使用方法

1. 访问系统
   打开浏览器访问 `http://localhost:12345`

2. 上传文件
   - 点击上传按钮或拖拽文件到上传区域
   - 设置文件有效期和下载次数限制
   - 获取分享链接和提取码

3. 下载文件
   - 访问分享链接
   - 输入提取码
   - 下载文件

4. 后台管理
   - 访问 `http://localhost:12345/#/admin`
   - 输入管理员密码：`FileCodeBox2023`
   - 进入后台管理页面
   - 查看系统信息、文件列表、用户管理等

## 下一步

- [存储配置](/guide/storage) - 了解如何配置不同的存储方式
- [安全设置](/guide/security) - 了解如何增强系统安全性
- [API 文档](/api/) - 了解如何通过 API 集成 