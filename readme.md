<div align="center">
<h1>文件快递柜-轻量</h1>
<h2>FileCodeBox-Lite</h2>
<p><em>匿名口令分享文本，文件，像拿快递一样取文件</em></p>
<p>交流Q群：739673698</p>
<p>使用AI解决问题：<a target='_blank' href='https://ailink.pw'>AiLink</a></p>
</div>

![banner](https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/static/banners/img_1.png)

---

[简体中文](./readme.md) | [English](./readme_en.md)

## 主要特色

- [x] 轻量简洁：Fastapi+Sqlite3+Vue2+ElementUI
- [x] 轻松上传：复制粘贴，拖拽选择
- [x] 多种类型：文本，文件
- [x] 防止爆破：错误次数限制
- [x] 防止滥用：IP限制上传次数
- [x] 口令分享：随机口令，存取文件，自定义次数以及有效期
- [x] 国际化：支持中文和英文
- [x] 匿名分享：无需注册，无需登录
- [x] 管理面板：查看所有文件，删除文件
- [x] 一键部署：docker一键部署
- [x] 自由拓展：S3协议、本地文件流，可根据需求在storage文件中新增存储引擎
- [x] 简单明了：适合新手练手项目
- [x] 终端下载：wget https://share.lanol.cn/share/select?code=83432

## 部署方式

### 1Panel一键部署

应用商店->实用工具->FileCodeBox
![img_6.png](./.github/images/img_6.png)
更新的话就是卸载重新安装即可
### Docker一键部署

#### 2.0版本，开发中

默认信息

后端地址：`/#/admin`

后台密码：`FileCodeBox2023`

AMD & ARM

一键安装

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:beta

```

一键更新

```bash
docker pull lanol/filecodebox:beta && docker stop filecodebox && docker rm filecodebox && docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:beta
```

#### 1.6版本AMD

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

#### 1.6版本ARM

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:arm
```

### 更新方式

```bash
// 更新
docker pull lanol/filecodebox:beta
// 停止容器并删除
docker stop filecodebox && docker rm filecodebox
// 重新运行容器
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

### 1.6版本注意

这一版改变比较大，如果出现问题可以尝试清空/opt/FileCodeBox目录，有问题欢迎反馈留言
注意，如果是第一次安装，请查看docker日志获取初始密码和后台地址，参考指令
后台本地文件列表，需要将服务器文件移动至目录/opt/FileCodeBox/data/locals，这样就可以显示了。

```bash
docker logs filecodebox

```

## 预览

### 例站

[https://share.lanol.cn](https://share.lanol.cn)

### 截图

<table style="width:100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="./.github/images/img.png" alt="寄文件">
</td>
<td style="width: 50%">
<img src="./.github/images/img_1.png" alt="寄文件">
</td>
</tr>
<tr style="width: 100%">
<td style="width: 50%">
<img src="./.github/images/img_2.png" alt="寄文件">
</td>
<td style="width: 50%">
<img src="./.github/images/img_3.png" alt="寄文件">
</td>
</tr>
<tr style="width: 100%">
<td style="width: 50%">
<img src="./.github/images/img_4.png" alt="寄文件">
</td>
<td style="width: 50%">
<img src="./.github/images/img_5.png" alt="寄文件">
</td>
</tr>
</table>

## 配置文件（1.7及以下版本才需要）

如果需要修改配置，可以将该文件放在`/opt/FileCodeBox/`目录下，并命名为`.env`，然后重启容器即可。
如果不是Docker，则需要在项目同目录下新建一个`data`文件夹，然后在创建`.env`文件

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

## 状态

![Alt](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vastsa/FileCodeBox&type=Date)](https://star-history.com/#vastsa/FileCodeBox&Date)

## 常见问题

1. 413 Request Entity Too Large
   Nginx限制：
   找到自己主机的nginx.conf配置文件，打开
   在http{}中加入 client_max_body_size 10m;
   然后重启nginx

## 免责声明

本项目开源仅供学习使用，不得用于任何违法用途，否则后果自负，与本人无关。使用请保留项目地址谢谢。
