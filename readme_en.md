<div align="center">
<h1>File Express Cabinet - Lite</h1>
<h2>FileCodeBox-Lite</h2>
<p><em>Anonymously share text and files, retrieve files like receiving packages</em></p>
<p>Communication Q group: 739673698, welcome everyone to brainstorm, project conceptual reconstruction</p>
</div>

![banner](https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/static/banners/img_1.png)

---

[Simplified Chinese](./readme.md) | [English](./readme_en.md)

## Main Features

- [x] Lightweight and concise: Fastapi+Sqlite3+Vue3+ElementUI
- [x] Easy upload: Copy and paste, drag and drop selection
- [x] Multiple types: Text, file
- [x] Prevent brute force: Limit the number of errors
- [x] Prevent abuse: Limit the number of uploads by IP
- [x] Password sharing: Random password, store and retrieve files, customize the number of times and validity period
- [x] Anonymous sharing: No registration, no login, no IP records
- [x] Management panel: View all files, delete files
- [x] One-click deployment: Docker one-click deployment
- [x] Free extension: S3 protocol, local file stream, can add storage engines in the storage file according to needs
- [x] Simple and clear: Suitable for beginners' practice projects

## Deployment Method

### Docker one-click deployment

#### Version 2.0, under development

Default information

Backend address: `/#/admin`

Backend password: `FileCodeBox2023`

AMD & ARM

One-click installation

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:beta

```

One-click update

```bash
docker pull lanol/filecodebox:beta && docker stop filecodebox && docker rm filecodebox && docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:beta
```

#### Version 1.6 AMD

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

#### Version 1.6 ARM

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:arm
```

### Baota deployment

Not recommended, outdated
https://www.yuque.com/lxyo/work/lc1oe0xqk8t9b976

### Version 1.6 Note

This version has relatively large changes. If there are any problems, you can try clearing the /opt/FileCodeBox directory. If you have any problems, please feel free to leave
feedback.
Note that if this is the first installation, please check the docker log to get the initial password and backend address, and refer to the instructions
For the local file list of the background, you need to move the server files to the directory /opt/FileCodeBox/data/locals so that they can be displayed.

```bash
docker logs filecodebox
```

## Preview

### Example site

[https://share.lanol.cn](https://share.lanol.cn)

### Dark mode

<table style="width:100%">

<tr style="width: 100%">
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_10.png" alt="Send files">

</td>
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_11.png" alt="Send files">

</td>
</tr>
</table>

### Sending

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_1.png" alt="Send files">
</td>
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_2.png" alt="Send text">
</td>
</tr>
<tr style="width: 100%;">
<td colspan="2" style="width: 100%;">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_3.png" alt="Send text">
</td>
</tr>
</table>

### Retrieving

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_6.png" alt="Retrieve">
</td>
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_5.png" alt="Wrong retrieval code">
</td>
</tr>
<tr style="width: 100%;">
<td colspan="2" style="width: 100%;">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_4.png" alt="Retrieve file">
</td>
</tr>
</table>

### Management

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_7.png" alt="admin">
</td>
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_12.png" alt="admin">
</td>
</tr>
<tr style="width: 100%;">
<td colspan="2" style="width: 100%;">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_13.png" alt="admin">
</td>
</tr>
</table>

## Configuration file (only required for version 1.7 and below)

If you need to modify the configuration, you can place this file in the `/opt/FileCodeBox/` directory and name it `.env`, then restart the container.
If it is not Docker, you need to create a `data` folder in the same directory as the project, and then create a `.env` file.

```dotenv
# 端口
PORT=12345
# Sqlite数据库文件
DATABASE_URL=sqlite+aiosqlite:///database.db
# 静态文件夹
DATA_ROOT=./static
# 静态文件夹URL
STATIC_URL=/static
# 开启上传
ENABLE_UPLOAD=True
# 错误次数
ERROR_COUNT=5
# 错误限制分钟数
ERROR_MINUTE=10
# 上传次数
UPLOAD_COUNT=60
# 上传限制分钟数
UPLOAD_MINUTE=1
# 删除过期文件的间隔（分钟）
DELETE_EXPIRE_FILES_INTERVAL=10
# 管理地址
ADMIN_ADDRESS=admin
# 管理密码
ADMIN_PASSWORD=admin
# 文件大小限制，默认10MB
FILE_SIZE_LIMIT=10
# 网站标题
TITLE=文件快递柜
# 网站描述
DESCRIPTION=FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件，图片，视频，音频，压缩包等文件
# 网站关键词
KEYWORDS=FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件，图片，视频，音频，压缩包等文件
# 存储引擎
STORAGE_ENGINE=filesystem
# 如果使用阿里云OSS服务的话需要额外创建如下参数：
# 阿里云账号AccessKey
KeyId=阿里云账号AccessKey
# 阿里云账号AccessKeySecret
KeySecret=阿里云账号AccessKeySecret
# 阿里云OSS Bucket的地域节点
OSS_ENDPOINT=阿里云OSS Bucket的地域节点
# 阿里云OSS Bucket的BucketName
BUCKET_NAME=阿里云OSS Bucket的BucketName
```

## Status

![Alt](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vastsa/FileCodeBox&type=Date)](https://star-history.com/#vastsa/FileCodeBox&Date)

## Appreciation

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%;text-align: center;">
Alipay
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_9.png" alt="Alipay">
</td>
<td style="width: 50%;text-align: center">
WeChat
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_8.png" alt="WeChat">
</td>
</tr>
</table>    

## Frequently Asked Questions

1. 413 Request Entity Too Large
   Nginx restriction:
   Find the nginx.conf configuration file of your host and open it.
   Add `client_max_body_size 10m;` inside the `http{}` block.
   Then restart nginx.

## Disclaimer

This project is open source and is intended for learning purposes only. It must not be used for any illegal purposes. Any consequences arising from such use are the sole
responsibility of the user and are not related to me. Please keep the project address when using. Thank you.
