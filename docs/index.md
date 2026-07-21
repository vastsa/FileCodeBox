---
layout: home

hero:
  name: "FileCodeBox"
  text: "像取快递一样取文件"
  tagline: 轻量、现代的自托管文件与文本分享服务
  image:
    src: /logo_small.png
    alt: FileCodeBox
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/getting-started
    - theme: alt
      text: 在线体验
      link: https://share.lanol.cn
    - theme: alt
      text: 部署指南
      link: /guide/getting-started#docker-部署推荐

features:
  - icon: 01
    title: 即传即取
    details: 文件与文本统一分享，支持批量、分片和断点续传
  - icon: 02
    title: 灵活失效
    details: 按时间或取件次数失效，也可以永久保留
  - icon: 03
    title: 数据自主
    details: 支持本地、S3、OneDrive、WebDAV 与 OpenDAL
---

## 30 秒启动

```bash
docker run -d --restart unless-stopped \
  -p 12345:12345 \
  -v ./data:/app/data \
  --name filecodebox \
  lanol/filecodebox:2.5.1 # x-release-please-version
```

打开 `http://localhost:12345`，按引导完成首次初始化。

<div class="doc-paths">
  <a class="doc-path" href="/guide/getting-started">
    <span>开始使用</span>
    <strong>部署、初始化与升级</strong>
    <small>从一台空服务器开始运行 FileCodeBox →</small>
  </a>
  <a class="doc-path" href="/guide/storage">
    <span>管理服务</span>
    <strong>存储、配置与安全</strong>
    <small>为生产环境选择合适的存储和保护策略 →</small>
  </a>
  <a class="doc-path" href="/api/">
    <span>集成开发</span>
    <strong>API 与上传流程</strong>
    <small>接入分享、分片上传和管理能力 →</small>
  </a>
</div>

::: warning 使用须知
请仅将 FileCodeBox 用于合法的文件与文本分享。服务运营者应自行负责部署安全、数据合规和内容管理。
:::
