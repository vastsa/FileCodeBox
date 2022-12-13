<div style="text-align: center">
<h1>File Express Cabinet </h1>
<p><em>share text and files with anonymous passwords, and take files like express delivery </em></p>
</div>

---

[English](./README_EN.md) | [简体中文](./README.md)

## Main features

- [x] lightweight and simple: Fastapi + Sqlite3 + Vue2 + ElementUI
- [x] easy upload: copy and paste, drag and drop
- [x] multiple types: Text, File
- [x] explosion Prevention: error count limit
- [x] prevent abuse: IP address limits the number of uploads
- [x] password sharing: random password, file access, custom times, and validity period
- [x] anonymous sharing: no registration, no login
- [x] management Panel: View all files and delete them
- [x] one-click deployment: docker one-click deployment

## Preview

### Send

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_1.png" alt="寄文件">
</td>
<td style="width: 50%">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_2.png" alt="寄文本">
</td>
</tr>
<tr style="width: 100%;">
<td colspan="2" style="width: 100%;">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_3.png" alt="寄文本">
</td>
</tr>
</table>

### Receive

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_6.png" alt="取件">
</td>
<td style="width: 50%">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_5.png" alt="取件码错误">
</td>
</tr>
<tr style="width: 100%;">
<td colspan="2" style="width: 100%;">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_4.png" alt="取文件">
</td>
</tr>
</table>

### Manage

![管理](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_7.png)

## Deployment method

### One-click Docker deployment

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

### Other methods

请参考->[部署文档](https://www.yuque.com/lxyo/work/zd0kvzy7fofx6w7v)

## Configuration file

if you need to modify the configuration, you can put the file in `/opt/FileCodeBox/` directory and name it `.env` , and
then
restart the container.

```bash

```dotenv
# 端口
PORT=12345
# Sqlite数据库文件
DATABASE_URL=sqlite+aiosqlite:///database.db
# 静态文件夹
DATA_ROOT=./static
# 静态文件夹URL
STATIC_URL=/static
# 错误次数
ERROR_COUNT=5
# 错误限制分钟数
ERROR_MINUTE=10
# 上传次数
UPLOAD_COUNT=60
# 上传限制分钟数
UPLOAD_MINUTE=1
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
```
