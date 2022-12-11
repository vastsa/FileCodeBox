# 文件快递柜

## 解决问题

很多时候，我们都想将一些文件或文本传送给别人，或者跨端传递一些信息，但是我们又不想为了分享，而去下载一些七里八里的软件，这时候，我们就可以使用口令传送箱，像拿快递一样取文件。

## 主要特色

- [x] 轻量简洁，Fastapi+sqlite3
- [x] 拖拽，复制粘贴上传
- [x] 文件口令传输，生成二维码
- [x] 分享文件：多种上传方式供你选择
- [x] 分享文本：直接复制粘贴直接上传
- [x] 防爆破：错误五次拉黑十分钟
- [x] 完全匿名：不记录任何信息
- [x] 无需注册：无需注册，无需登录
- [x] Sqlite3数据库：无需安装数据库
- [x] 可以加get参数code，这样打开就会读取取件码如：http://xxx.com?code=12345
- [x] 管理面板：简单列表页删除违规文件
- [x] 口令使用次数，口令有效期，二维码分享

## 更新记录

### 2022年12月10日 01:56:43

1. 管理面板已新增，一如既往的极简，只有删除
2. 二维码图片（调用的网络接口，如果离线环境将无法使用，一切为了极简）

### 2022年12月10日 21:10:00

1. 取件码有效期，取件码使用次数
2. 优化代码逻辑
3. 限制上传文件大小
4. 完善配置参数

### 2022年12月10日 23:50:00

1. 修复取件不显示码的问题
2. 修复文件次数为1时，文件被删除的问题

## 系统截图

### 2022年12月11日 14:55:00

1. 隐藏文件真实地址

### 取件

![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img.png)
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_1.png)

### 寄件

![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_2.png)
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_3.png)

### 管理面板

![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_4.png)
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_5.png)

## 部署教程

https://www.yuque.com/lxyo/work/zd0kvzy7fofx6w7v

## 部署方式

先拉取代码，然后修改main.py文件，将里面写了注释的可以根据需求改一下

### 服务端部署

1. 安装Python3
2. 拉取代码，解压缩
3. 安装依赖包：`pip install -r requirements.txt`
4. 运行` uvicorn main:app --host 0.0.0.0 --port 12345`
5. 然后你自己看怎么进程守护吧

### 宝塔部署

1. 安装宝塔Python Manager
2. 然后你自己看着填吧

### Docker部署

```bash
docker build --file Dockerfile --tag filecodebox .
docker run -d -p 12345:12345 --name filecodebox filecodebox
```

## 状态

![Alt](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg "Repobeats analytics image")

## 免责声明

本项目开源仅供学习使用，不得用于商业用途以及任何违法用途，否则后果自负，与本人无关。使用请保留项目地址谢谢。
