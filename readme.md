<div align="center">
<h1>文件快递柜-轻量</h1>
<h2>FileCodeBox-Lite</h2>
<p><em>匿名口令分享文本，文件，像拿快递一样取文件</em></p>
<p>交流Q群：739673698，欢迎各位集思广益，项目构思重构中</p>
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
- [x] 匿名分享：无需注册，无需登录
- [x] 管理面板：查看所有文件，删除文件
- [x] 一键部署：docker一键部署
- [x] 自由拓展：阿里云OSS、本地文件流，可根据需求在storage文件中新增存储引擎
- [x] 简单明了：适合新手练手项目

## 部署方式

### Docker一键部署

#### AMD 开发版（不稳定，待测试，新增分片异步上传，永久存储，不建议使用，很多没发现的坑）

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:pre

```

#### AMD

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

#### ARM

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:arm
```

### 宝塔部署

https://www.yuque.com/lxyo/work/lc1oe0xqk8t9b976

### 更新方式

```bash
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

### 其他方式

仅供参考，历史版本->[部署文档](https://www.yuque.com/lxyo/work/zd0kvzy7fofx6w7v)

## 项目规划

2022年12月14日
这个项目的灵感来源于丁丁快传，然后写了这么一个基于本机存储的快传系统，本系统主要是以轻量，单用户，离线环境（`私有化`
）为主，因此也不需要加太多东西，所以其实这个项目到这基本功能已经完成了，剩下的就是维护和完善现有功能。
也不会再加入新的大功能了，如果你有更好的想法和建议欢迎提issue。

## 预览

### 例站

[https://share.lanol.cn](https://share.lanol.cn)

### 暗黑模式

<table style="width:100%">

<tr style="width: 100%">
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_10.png" alt="寄文件">

</td>
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_11.png" alt="寄文件">

</td>
</tr>
</table>

### 寄件

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_1.png" alt="寄文件">
</td>
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_2.png" alt="寄文本">
</td>
</tr>
<tr style="width: 100%;">
<td colspan="2" style="width: 100%;">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_3.png" alt="寄文本">
</td>
</tr>
</table>

### 取件

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_6.png" alt="取件">
</td>
<td style="width: 50%">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_5.png" alt="取件码错误">
</td>
</tr>
<tr style="width: 100%;">
<td colspan="2" style="width: 100%;">
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_4.png" alt="取文件">
</td>
</tr>
</table>

### 管理

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

## 配置文件

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

## 接口文档

前端比较简陋，可以使用接口进行二次开发

### 取件

#### PATH

`/`

#### METHOD

`POST`

#### PARAMS

code: 取件码

#### Response

```json
{
  "detail": "msg",
  "data": {
    "type": "类型",
    "text": "文本",
    "name": "名称",
    "code": "取件码"
  }
}
```

### 寄件

#### PATH

`/share`

#### METHOD

`POST`

#### PARAMS

style: 1为次数，2为时间
value: 次数或时间
text: 取件码
file: 文件

#### Response

```json
{
  "detail": "msg",
  "data": {
    "code": "类型",
    "key": "唯一ID",
    "name": "名称"
  }
}
```

## 状态

![Alt](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vastsa/FileCodeBox&type=Date)](https://star-history.com/#vastsa/FileCodeBox&Date)

## 赞赏

<table style="width: 100%">
<tr style="width: 100%">
<td style="width: 50%;text-align: center;">
支付宝
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_9.png" alt="支付宝">
</td>
<td style="width: 50%;text-align: center">
微信
<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/images/img_8.png" alt="微信">
</td>
</tr>
</table>    

## 常见问题

1. 413 Request Entity Too Large
   Nginx限制：
   找到自己主机的nginx.conf配置文件，打开
   在http{}中加入 client_max_body_size 10m;
   然后重启nginx

## 免责声明

本项目开源仅供学习使用，不得用于任何违法用途，否则后果自负，与本人无关。使用请保留项目地址谢谢。
