# 口令传送箱

## 主要特色

- [x] 拖拽，复制粘贴上传
- [x] 文件口令传输
- [x] 分享文件：多种上传方式供你选择
- [x] 分享文本：直接复制粘贴直接上传
- [x] 防爆破：错误五次拉黑十分钟
- [x] 完全匿名：不记录任何信息
- [x] 无需注册：无需注册，无需登录
- [x] Sqlite3数据库：无需安装数据库

## 系统截图
![取件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/%E5%8F%96%E4%BB%B6.png)
![取件箱](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/%E5%8F%96%E4%BB%B6%E7%AE%B1.png)
![寄件](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/%E5%AF%84%E4%BB%B6.png)
![寄件箱](https://raw.githubusercontent.com/vastsa/FileCodeBox/master/images/%E5%AF%84%E4%BB%B6%E7%AE%B1.png)

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
