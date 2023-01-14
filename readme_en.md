<div align="center">
<h1>File Express Cabinet - Lite</h1>
<h2>FileCodeBox - Lite</h2>
<p><em>share text and files with anonymous passwords, and take files like express delivery </em></p>
</div>

![banner](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/static/banners/img_1.png)


---

[简体中文](./readme.md) | [English](./readme_en.md)

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

## Deployment method

### One-click Docker deployment

#### AMD

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

#### ARM

```bash
docker run -d --restart=always -p 12345:12345 -v /Users/lan/soft/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:arm
```

### Update

```bash
// 找到容器ID
docker ps -a
// 停止容器并删除
docker stop 容器ID && docker rm 容器ID
// 重新运行容器
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

### Other methods

For reference only, historical version->[部署文档](https://www.yuque.com/lxyo/work/zd0kvzy7fofx6w7v)

## Project Plan

December 14, 2022
This project is mainly light-weight, mainly single-user, offline environment, so there is no need to add too many
things, so in fact, the basic functions of this project have been completed, and the rest is to maintain and improve the
existing functions.

No new major functions will be added. If there are new functions, it will be our Pro version. Of course, it will
continue to be open source. It is an honor to be open source with @veoco. I learned from his code Many, I basically used
the Django set before, and only used Fastapi. Many of his writing methods have benefited me a lot, and I have a deeper
understanding of Fastapi, so I will also use Fastapi in the Pro version .

According to some current feedback, I hope to add multi-user functions and multi-storage engines, etc. Welcome to
continue to give comments and join us in joint development.

If you have better ideas and suggestions, welcome to file an issue.

## Preview

### Demo

[https://share.lanol.cn](https://share.lanol.cn)

### Dark Theme

<table style="width:100%">

<tr style="width: 100%">
<td style="width: 50%">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_10.png" alt="寄文件">

</td>
<td style="width: 50%">
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_11.png" alt="寄文件">

</td>
</tr>
</table>

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

## Configuration file

if you need to modify the configuration, you can put the file in `/opt/FileCodeBox/` directory and name it `.env` , and
then restart the container.
If it is not Docker, you need to create a `data` folder in the same directory as the project, and then create a `.env`
file

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
```

## Status

![Alt](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vastsa/FileCodeBox&type=Date)](https://star-history.com/#vastsa/FileCodeBox&Date)

## Appreciate

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%;text-align: center;">
支付宝
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_9.png" alt="支付宝">
</td>
<td style="width: 50%;text-align: center">
微信
<img src="https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_8.png" alt="微信">
</td>
</tr>
</table>    

## Disclaimer

this project is open source for learning only and cannot be used for any illegal purposes. Otherwise, you will be
responsible for the consequences and have nothing to do with yourself. Please keep the project address. Thank you.