# 口令传送箱

## 解决问题

很多时候，我们都想将一些文件或文本传送给别人，或者跨端传递一些信息，但是我们又不想为了分享，而去下载一些七里八里端软件，这时候，我们就可以使用口令传送箱。

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
- [ ] 管理面板：简单列表页删除违规文件
- [ ] 口令使用次数，口令有效期，二维码分享

## 系统截图
### 取件
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img.png)
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_1.png)
### 寄件
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_2.png)
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_3.png)
### 管理面板
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_4.png)
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/img_5.png)

## 部署方式

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

## 免责声明

本项目开源仅供学习使用，不得用于商业用途以及任何违法用途，否则后果自负，与本人无关。