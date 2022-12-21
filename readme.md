<div style="text-align: center">
<h1>文件快递柜-轻量</h1>
<h2>FileCoxBox-Lite</h2>
<p><em>匿名口令分享文本，文件，像拿快递一样取文件</em></p>
</div>

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

## 部署方式

### Docker一键部署

#### AMD

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:latest
```

#### ARM

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:arm
```

### 其他方式

仅供参考，历史版本->[部署文档](https://www.yuque.com/lxyo/work/zd0kvzy7fofx6w7v)

## 项目规划

2022年12月14日

这个项目的灵感来源于丁丁快传，然后写了这么一个基于本机存储的快传系统，本系统主要是以轻量，单用户，离线环境（`私有化`
）为主，因此也不需要加太多东西，所以其实这个项目到这基本功能已经完成了，剩下的就是维护和完善现有功能。

也不会再加入新的大功能了，如果有新的功能的话，那就是我们的Pro版本了，当然也是继续开源的，能和@veoco一起开源挺荣幸的，在他的代码中我学到了许多，此前我基本上是使用Django那一套，对Fastapi仅限于使用，他的许多写法让我受益匪浅，也让我对Fastapi有了更深的了解，所以我也会在Pro版本中使用Fastapi。

根据目前一些使用反馈来说，希望加入登录功能，还有多存储引擎等，欢迎各位继续提意见，加入我们共同开发。

如果你有更好的想法和建议欢迎提issue。

## 预览

### 例站

[https://share.lanol.cn](https://share.lanol.cn)

### 暗黑模式

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

### 寄件

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

### 取件

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

### 管理

![管理](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_7.png)

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
```

## 状态

![Alt](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg "Repobeats analytics image")

## 赞赏

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

## 常见问题

1. 413 Request Entity Too Large
   Nginx限制：
   找到自己主机的nginx.conf配置文件，打开
   在http{}中加入 client_max_body_size 10m;
   然后重启nginx

## 免责声明

本项目开源仅供学习使用，不得用于任何违法用途，否则后果自负，与本人无关。使用请保留项目地址谢谢。
