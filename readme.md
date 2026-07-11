<div align="center">

<img src="./docs/public/logo_small.png" alt="FileCodeBox" width="96" />

# FileCodeBox

### 像取快递一样取文件

一个轻量、现代的自托管文件分享工具。无需注册，上传后获得口令，对方输入即可取件。

[在线演示](https://share.lanol.cn)　·　[使用文档](https://fcb-docs.aiuo.net/)　·　[English](./readme_en.md)

[![Release](https://img.shields.io/github/v/release/vastsa/FileCodeBox?style=flat-square&color=111111)](https://github.com/vastsa/FileCodeBox/releases/latest)
[![Docker Pulls](https://img.shields.io/docker/pulls/lanol/filecodebox?style=flat-square&logo=docker&color=111111)](https://hub.docker.com/r/lanol/filecodebox)
[![Stars](https://img.shields.io/github/stars/vastsa/FileCodeBox?style=flat-square&logo=github&color=111111)](https://github.com/vastsa/FileCodeBox/stargazers)
[![License](https://img.shields.io/github/license/vastsa/FileCodeBox?style=flat-square&color=111111)](./LICENSE)

<br />

<img src="./.github/images/readme/retrieve-dark.png" alt="FileCodeBox 取件页面" width="860" />

</div>

## 一条命令开始

```bash
docker run -d --restart unless-stopped -p 12345:12345 -v ./data:/app/data --name filecodebox lanol/filecodebox:2.5.0 # x-release-please-version
```

访问 `http://localhost:12345`，完成首次初始化。生产环境建议固定版本号；`latest` 指向最新正式版。

## 简单，但足够强大

<table>
<tr>
<td width="33%" valign="top"><b>即传即取</b><br /><sub>文件与文本统一分享，支持拖拽、粘贴、批量与分片上传。</sub></td>
<td width="33%" valign="top"><b>按需失效</b><br /><sub>按时间、取件次数或永久保存，自动清理过期内容。</sub></td>
<td width="33%" valign="top"><b>数据自主</b><br /><sub>本地、S3、OneDrive、WebDAV 与 OpenDAL，数据留在自己的基础设施。</sub></td>
</tr>
</table>

## 从分享，到管理

<table>
<tr>
<td width="50%"><img src="./.github/images/readme/send.png" alt="文件发送页面" /></td>
<td width="50%"><img src="./.github/images/readme/dashboard.png" alt="管理仪表盘" /></td>
</tr>
</table>

<p align="center">
  <img src="./.github/images/readme/mobile-retrieve.png" alt="移动端取件" width="29%" />
  &nbsp;&nbsp;
  <img src="./.github/images/readme/mobile-send.png" alt="移动端发送" width="29%" />
  &nbsp;&nbsp;
  <img src="./.github/images/readme/mobile-files.png" alt="移动端管理" width="29%" />
</p>

<div align="center">

`FastAPI`　`Vue 3`　`SQLite`　`Docker`　`S3`　`WebDAV`　`Dark Mode`

</div>

## 继续了解

- [快速开始](https://fcb-docs.aiuo.net/guide/getting-started) · 部署、初始化与升级
- [存储配置](https://fcb-docs.aiuo.net/guide/storage) · 本地与对象存储
- [安全设置](https://fcb-docs.aiuo.net/guide/security) · 限流、会话与访问保护
- [API 文档](https://fcb-docs.aiuo.net/api/) · 上传、取件与管理接口
- [前端源码](https://github.com/vastsa/FileCodeBoxFronted) · 当前 2024 主题

## 参与项目

欢迎 [提交 Issue](https://github.com/vastsa/FileCodeBox/issues/new/choose) 或 Pull Request。项目基于 [LGPL-3.0](./LICENSE) 发布。

## 免责声明

本项目仅供合法的文件与文本分享场景使用。请勿上传、存储或传播违法、侵权或未经授权的内容；使用者应自行承担部署、数据合规与内容管理责任。

<div align="center">

**如果 FileCodeBox 对你有帮助，欢迎点亮一个 Star。**

</div>
