# 存储配置

FileCodeBox 支持多种存储后端，您可以根据需求选择合适的存储方式。本文档将详细介绍各种存储后端的配置方法。

## 存储类型概览

| 存储类型 | 配置值 | 说明 |
|---------|--------|------|
| 本地存储 | `local` | 默认存储方式，文件保存在服务器本地 |
| S3 兼容存储 | `s3` | 支持 AWS S3、阿里云 OSS、MinIO 等 |
| OneDrive | `onedrive` | 微软 OneDrive 云存储（仅支持工作/学校账户） |
| WebDAV | `webdav` | 支持 WebDAV 协议的存储服务 |
| OpenDAL | `opendal` | 通过 OpenDAL 集成更多存储服务 |

## 本地存储

本地存储是默认的存储方式，文件将保存在服务器的 `data/` 目录下。

### 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file_storage` | string | `local` | 存储类型 |
| `storage_path` | string | `""` | 自定义存储路径（可选） |

### 配置示例

```bash
file_storage=local
storage_path=
```

### 说明

- 文件默认存储在 `data/share/data/` 目录下
- 按日期自动创建子目录：`年/月/日/文件ID/`
- 建议在生产环境中将 `data/` 目录挂载到持久化存储

## S3 兼容存储

支持所有 S3 兼容的对象存储服务，包括 AWS S3、阿里云 OSS、MinIO、腾讯云 COS 等。

### 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file_storage` | string | - | 设置为 `s3` |
| `s3_access_key_id` | string | `""` | Access Key ID |
| `s3_secret_access_key` | string | `""` | Secret Access Key |
| `s3_bucket_name` | string | `""` | 存储桶名称 |
| `s3_endpoint_url` | string | `""` | S3 端点 URL |
| `s3_region_name` | string | `auto` | 区域名称 |
| `s3_signature_version` | string | `s3v2` | 签名版本（`s3v2` 或 `s3v4`） |
| `s3_hostname` | string | `""` | S3 主机名（备用） |
| `s3_proxy` | int | `0` | 是否通过服务器代理下载（1=是，0=否） |
| `aws_session_token` | string | `""` | AWS 会话令牌（可选） |

### AWS S3 配置示例

```bash
file_storage=s3
s3_access_key_id=AKIAIOSFODNN7EXAMPLE
s3_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
s3_bucket_name=my-filecodebox-bucket
s3_endpoint_url=https://s3.amazonaws.com
s3_region_name=us-east-1
s3_signature_version=s3v4
```

### 阿里云 OSS 配置示例

```bash
file_storage=s3
s3_access_key_id=您的AccessKeyId
s3_secret_access_key=您的SecretAccessKey
s3_bucket_name=bucket-name
s3_endpoint_url=https://bucket-name.oss-cn-hangzhou.aliyuncs.com
s3_region_name=oss-cn-hangzhou
s3_signature_version=s3v4
```

::: tip 阿里云 OSS 端点格式
端点 URL 格式为：`https://<bucket-name>.<region>.aliyuncs.com`

常用区域：
- 杭州：`oss-cn-hangzhou`
- 上海：`oss-cn-shanghai`
- 北京：`oss-cn-beijing`
- 深圳：`oss-cn-shenzhen`
:::

### MinIO 配置示例

```bash
file_storage=s3
s3_access_key_id=minioadmin
s3_secret_access_key=minioadmin
s3_bucket_name=filecodebox
s3_endpoint_url=http://localhost:9000
s3_region_name=us-east-1
s3_signature_version=s3v4
```

::: warning MinIO 注意事项
- `s3_endpoint_url` 填写 MinIO 的 API 接口地址
- `s3_region_name` 根据 MinIO 配置中的 `Server Location` 设置
- 确保存储桶已创建且有正确的访问权限
:::

### 腾讯云 COS 配置示例

```bash
file_storage=s3
s3_access_key_id=您的SecretId
s3_secret_access_key=您的SecretKey
s3_bucket_name=bucket-name-1250000000
s3_endpoint_url=https://cos.ap-guangzhou.myqcloud.com
s3_region_name=ap-guangzhou
s3_signature_version=s3v4
```

### 代理下载

当 `s3_proxy=1` 时，文件下载将通过服务器中转，而不是直接从 S3 下载。这在以下情况下有用：

- S3 存储桶不允许公开访问
- 需要隐藏实际的存储地址
- 网络环境限制直接访问 S3



## OneDrive 存储

OneDrive 存储支持将文件保存到微软 OneDrive 云存储。

::: warning 重要限制
OneDrive 存储**仅支持工作或学校账户**，并且需要有管理员权限以授权 API。个人账户无法使用此功能。
:::

### 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file_storage` | string | - | 设置为 `onedrive` |
| `onedrive_domain` | string | `""` | Azure AD 域名 |
| `onedrive_client_id` | string | `""` | 应用程序（客户端）ID |
| `onedrive_username` | string | `""` | 账户邮箱 |
| `onedrive_password` | string | `""` | 账户密码 |
| `onedrive_root_path` | string | `filebox_storage` | OneDrive 中的存储根目录 |
| `onedrive_proxy` | int | `0` | 是否通过服务器代理下载 |

### 配置示例

```bash
file_storage=onedrive
onedrive_domain=contoso.onmicrosoft.com
onedrive_client_id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
onedrive_username=user@contoso.onmicrosoft.com
onedrive_password=your_password
onedrive_root_path=filebox_storage
```

### Azure 应用注册步骤

要使用 OneDrive 存储，您需要在 Azure 门户中注册应用程序：

#### 1. 获取域名

登录 [Azure 门户](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)，将鼠标置于右上角账号处，浮窗显示的**域**即为 `onedrive_domain` 的值。

#### 2. 注册应用

1. 点击左上角的 **+ 新注册**
2. 输入应用名称（如：FileCodeBox）
3. **受支持的帐户类型**：选择"任何组织目录(任何 Azure AD 目录 - 多租户)中的帐户和个人 Microsoft 帐户"
4. **重定向 URI**：选择 `Web`，输入 `http://localhost`
5. 点击**注册**

#### 3. 获取客户端 ID

注册完成后，在应用概述页面的**概要**中找到**应用程序(客户端)ID**，即为 `onedrive_client_id` 的值。

#### 4. 配置身份验证

1. 在左侧菜单选择**身份验证**
2. 找到**允许公共客户端流**，选择**是**
3. 点击**保存**

#### 5. 配置 API 权限

1. 在左侧菜单选择 **API 权限**
2. 点击 **+ 添加权限**
3. 选择 **Microsoft Graph** → **委托的权限**
4. 勾选以下权限：
   - `openid`
   - `Files.Read`
   - `Files.Read.All`
   - `Files.ReadWrite`
   - `Files.ReadWrite.All`
   - `User.Read`
5. 点击**添加权限**
6. 点击**代表 xxx 授予管理员同意**
7. 确认后，权限状态应显示为**已授予**

### 安装依赖

使用 OneDrive 存储需要安装额外的 Python 依赖：

```bash
pip install msal Office365-REST-Python-Client
```

### 验证配置

您可以使用以下代码测试配置是否正确：

```python
import msal
from office365.graph_client import GraphClient

domain = 'your_domain'
client_id = 'your_client_id'
username = 'your_username'
password = 'your_password'

def acquire_token_pwd():
    authority_url = f'https://login.microsoftonline.com/{domain}'
    app = msal.PublicClientApplication(
        authority=authority_url,
        client_id=client_id
    )
    result = app.acquire_token_by_username_password(
        username=username,
        password=password,
        scopes=['https://graph.microsoft.com/.default']
    )
    return result

# 测试连接
client = GraphClient(acquire_token_pwd)
me = client.me.get().execute_query()
print(f"登录成功：{me.user_principal_name}")
```

## WebDAV 存储

WebDAV 存储支持将文件保存到任何支持 WebDAV 协议的服务，如 Nextcloud、ownCloud、坚果云等。

### 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file_storage` | string | - | 设置为 `webdav` |
| `webdav_url` | string | `""` | WebDAV 服务器 URL |
| `webdav_username` | string | `""` | WebDAV 用户名 |
| `webdav_password` | string | `""` | WebDAV 密码 |
| `webdav_root_path` | string | `filebox_storage` | WebDAV 中的存储根目录 |
| `webdav_proxy` | int | `0` | 是否通过服务器代理下载 |

### 配置示例

```bash
file_storage=webdav
webdav_url=https://dav.example.com/remote.php/dav/files/username/
webdav_username=your_username
webdav_password=your_password
webdav_root_path=filebox_storage
```

### Nextcloud 配置示例

```bash
file_storage=webdav
webdav_url=https://your-nextcloud.com/remote.php/dav/files/username/
webdav_username=your_username
webdav_password=your_app_password
webdav_root_path=FileCodeBox
```

::: tip Nextcloud 应用密码
建议在 Nextcloud 中创建应用密码，而不是使用主密码：
1. 登录 Nextcloud
2. 进入**设置** → **安全**
3. 在**设备与会话**中创建新的应用密码
:::

### 坚果云配置示例

```bash
file_storage=webdav
webdav_url=https://dav.jianguoyun.com/dav/
webdav_username=your_email@example.com
webdav_password=your_app_password
webdav_root_path=FileCodeBox
```

::: tip 坚果云应用密码
坚果云需要使用应用密码：
1. 登录坚果云网页版
2. 进入**账户信息** → **安全选项**
3. 添加应用密码
:::

## OpenDAL 存储

OpenDAL 是一个统一的数据访问层，支持多种存储服务。通过 OpenDAL，您可以使用 Google Cloud Storage、Azure Blob Storage 等更多存储服务。

### 配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_storage` | string | 设置为 `opendal` |
| `opendal_scheme` | string | 存储服务类型（如 `gcs`、`azblob`） |
| `opendal_<scheme>_<setting>` | string | 服务特定的配置参数 |

### 安装依赖

```bash
pip install opendal
```

### Google Cloud Storage 配置示例

```bash
file_storage=opendal
opendal_scheme=gcs
opendal_gcs_root=/filecodebox
opendal_gcs_bucket=your-bucket-name
opendal_gcs_credential=base64_encoded_credential
```

### Azure Blob Storage 配置示例

```bash
file_storage=opendal
opendal_scheme=azblob
opendal_azblob_root=/filecodebox
opendal_azblob_container=your-container
opendal_azblob_account_name=your_account
opendal_azblob_account_key=your_key
```

### 支持的服务

OpenDAL 支持众多存储服务，完整列表请参考 [OpenDAL 官方文档](https://opendal.apache.org/docs/rust/opendal/services/index.html)。

常用服务包括：
- `gcs` - Google Cloud Storage
- `azblob` - Azure Blob Storage
- `obs` - 华为云 OBS
- `oss` - 阿里云 OSS（通过 OpenDAL）
- `cos` - 腾讯云 COS（通过 OpenDAL）
- `hdfs` - Hadoop HDFS
- `ftp` - FTP 服务器
- `sftp` - SFTP 服务器

::: warning OpenDAL 注意事项
1. 通过 OpenDAL 集成的服务均通过服务器中转下载，会同时消耗存储服务和服务器的流量
2. 相比原生 S3/OneDrive 支持，OpenDAL 方式可能缺少一些调试信息
3. OpenDAL 采用 Rust 编写，性能较好
:::

## 存储选择建议

| 场景 | 推荐存储 | 原因 |
|------|----------|------|
| 个人/小型部署 | 本地存储 | 简单易用，无需额外配置 |
| 企业内网 | MinIO + S3 | 自建对象存储，数据可控 |
| 公有云部署 | 对应云厂商 S3 | 同区域访问快，成本低 |
| 已有 OneDrive | OneDrive | 利用现有资源 |
| 已有 WebDAV | WebDAV | 兼容性好 |
| 特殊存储需求 | OpenDAL | 支持更多存储服务 |

## 常见问题

### S3 上传失败

1. 检查 Access Key 和 Secret Key 是否正确
2. 确认存储桶名称和区域配置正确
3. 检查存储桶的访问权限设置
4. 确认签名版本（`s3v2` 或 `s3v4`）与服务商要求一致

### OneDrive 认证失败

1. 确认使用的是工作/学校账户，而非个人账户
2. 检查 Azure 应用是否已授予管理员同意
3. 确认 API 权限配置完整
4. 验证用户名和密码是否正确

### WebDAV 连接失败

1. 检查 WebDAV URL 格式是否正确
2. 确认用户名和密码（或应用密码）正确
3. 检查服务器是否支持 WebDAV 协议
4. 确认网络连接正常
