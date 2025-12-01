# Storage Configuration

FileCodeBox supports multiple storage backends. You can choose the appropriate storage method based on your needs. This document details the configuration methods for various storage backends.

## Storage Types Overview

| Storage Type | Config Value | Description |
|--------------|--------------|-------------|
| Local Storage | `local` | Default storage method, files saved on local server |
| S3-Compatible Storage | `s3` | Supports AWS S3, Aliyun OSS, MinIO, etc. |
| OneDrive | `onedrive` | Microsoft OneDrive cloud storage (work/school accounts only) |
| WebDAV | `webdav` | Storage services supporting WebDAV protocol |
| OpenDAL | `opendal` | Integrate more storage services via OpenDAL |

## Local Storage

Local storage is the default storage method. Files are saved in the server's `data/` directory.

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_storage` | string | `local` | Storage type |
| `storage_path` | string | `""` | Custom storage path (optional) |

### Configuration Example

```bash
file_storage=local
storage_path=
```

### Notes

- Files are stored by default in `data/share/data/` directory
- Subdirectories are automatically created by date: `year/month/day/fileID/`
- In production, it's recommended to mount the `data/` directory to persistent storage

## S3-Compatible Storage

Supports all S3-compatible object storage services, including AWS S3, Aliyun OSS, MinIO, Tencent Cloud COS, etc.

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_storage` | string | - | Set to `s3` |
| `s3_access_key_id` | string | `""` | Access Key ID |
| `s3_secret_access_key` | string | `""` | Secret Access Key |
| `s3_bucket_name` | string | `""` | Bucket name |
| `s3_endpoint_url` | string | `""` | S3 endpoint URL |
| `s3_region_name` | string | `auto` | Region name |
| `s3_signature_version` | string | `s3v2` | Signature version (`s3v2` or `s3v4`) |
| `s3_hostname` | string | `""` | S3 hostname (alternative) |
| `s3_proxy` | int | `0` | Download through server proxy (1=yes, 0=no) |
| `aws_session_token` | string | `""` | AWS session token (optional) |


### AWS S3 Configuration Example

```bash
file_storage=s3
s3_access_key_id=AKIAIOSFODNN7EXAMPLE
s3_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
s3_bucket_name=my-filecodebox-bucket
s3_endpoint_url=https://s3.amazonaws.com
s3_region_name=us-east-1
s3_signature_version=s3v4
```

### Aliyun OSS Configuration Example

```bash
file_storage=s3
s3_access_key_id=YourAccessKeyId
s3_secret_access_key=YourSecretAccessKey
s3_bucket_name=bucket-name
s3_endpoint_url=https://bucket-name.oss-cn-hangzhou.aliyuncs.com
s3_region_name=oss-cn-hangzhou
s3_signature_version=s3v4
```

::: tip Aliyun OSS Endpoint Format
Endpoint URL format: `https://<bucket-name>.<region>.aliyuncs.com`

Common regions:
- Hangzhou: `oss-cn-hangzhou`
- Shanghai: `oss-cn-shanghai`
- Beijing: `oss-cn-beijing`
- Shenzhen: `oss-cn-shenzhen`
:::

### MinIO Configuration Example

```bash
file_storage=s3
s3_access_key_id=minioadmin
s3_secret_access_key=minioadmin
s3_bucket_name=filecodebox
s3_endpoint_url=http://localhost:9000
s3_region_name=us-east-1
s3_signature_version=s3v4
```

::: warning MinIO Notes
- `s3_endpoint_url` should be the MinIO API interface address
- `s3_region_name` should match the `Server Location` in MinIO configuration
- Ensure the bucket is created and has correct access permissions
:::

### Tencent Cloud COS Configuration Example

```bash
file_storage=s3
s3_access_key_id=YourSecretId
s3_secret_access_key=YourSecretKey
s3_bucket_name=bucket-name-1250000000
s3_endpoint_url=https://cos.ap-guangzhou.myqcloud.com
s3_region_name=ap-guangzhou
s3_signature_version=s3v4
```

### Proxy Download

When `s3_proxy=1`, file downloads are proxied through the server instead of directly from S3. This is useful when:

- S3 bucket doesn't allow public access
- Need to hide the actual storage address
- Network environment restricts direct S3 access

## OneDrive Storage

OneDrive storage supports saving files to Microsoft OneDrive cloud storage.

::: warning Important Limitation
OneDrive storage **only supports work or school accounts** and requires admin permissions to authorize the API. Personal accounts cannot use this feature.
:::

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_storage` | string | - | Set to `onedrive` |
| `onedrive_domain` | string | `""` | Azure AD domain |
| `onedrive_client_id` | string | `""` | Application (client) ID |
| `onedrive_username` | string | `""` | Account email |
| `onedrive_password` | string | `""` | Account password |
| `onedrive_root_path` | string | `filebox_storage` | Storage root directory in OneDrive |
| `onedrive_proxy` | int | `0` | Download through server proxy |

### Configuration Example

```bash
file_storage=onedrive
onedrive_domain=contoso.onmicrosoft.com
onedrive_client_id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
onedrive_username=user@contoso.onmicrosoft.com
onedrive_password=your_password
onedrive_root_path=filebox_storage
```

### Azure App Registration Steps

To use OneDrive storage, you need to register an application in the Azure portal:

#### 1. Get Domain

Log in to [Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade), hover over your account in the top right corner, and the **Domain** shown in the popup is the `onedrive_domain` value.

#### 2. Register Application

1. Click **+ New registration** in the top left
2. Enter application name (e.g., FileCodeBox)
3. **Supported account types**: Select "Accounts in any organizational directory (Any Azure AD directory - Multitenant) and personal Microsoft accounts"
4. **Redirect URI**: Select `Web`, enter `http://localhost`
5. Click **Register**

#### 3. Get Client ID

After registration, find the **Application (client) ID** in the **Essentials** section on the app overview page. This is the `onedrive_client_id` value.

#### 4. Configure Authentication

1. Select **Authentication** in the left menu
2. Find **Allow public client flows**, select **Yes**
3. Click **Save**

#### 5. Configure API Permissions

1. Select **API permissions** in the left menu
2. Click **+ Add a permission**
3. Select **Microsoft Graph** → **Delegated permissions**
4. Check the following permissions:
   - `openid`
   - `Files.Read`
   - `Files.Read.All`
   - `Files.ReadWrite`
   - `Files.ReadWrite.All`
   - `User.Read`
5. Click **Add permissions**
6. Click **Grant admin consent for xxx**
7. After confirmation, permission status should show **Granted**

### Install Dependencies

Using OneDrive storage requires additional Python dependencies:

```bash
pip install msal Office365-REST-Python-Client
```

### Verify Configuration

You can use the following code to test if the configuration is correct:

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

# Test connection
client = GraphClient(acquire_token_pwd)
me = client.me.get().execute_query()
print(f"Login successful: {me.user_principal_name}")
```


## WebDAV Storage

WebDAV storage supports saving files to any service that supports the WebDAV protocol, such as Nextcloud, ownCloud, Nutstore, etc.

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_storage` | string | - | Set to `webdav` |
| `webdav_url` | string | `""` | WebDAV server URL |
| `webdav_username` | string | `""` | WebDAV username |
| `webdav_password` | string | `""` | WebDAV password |
| `webdav_root_path` | string | `filebox_storage` | Storage root directory in WebDAV |
| `webdav_proxy` | int | `0` | Download through server proxy |

### Configuration Example

```bash
file_storage=webdav
webdav_url=https://dav.example.com/remote.php/dav/files/username/
webdav_username=your_username
webdav_password=your_password
webdav_root_path=filebox_storage
```

### Nextcloud Configuration Example

```bash
file_storage=webdav
webdav_url=https://your-nextcloud.com/remote.php/dav/files/username/
webdav_username=your_username
webdav_password=your_app_password
webdav_root_path=FileCodeBox
```

::: tip Nextcloud App Password
It's recommended to create an app password in Nextcloud instead of using your main password:
1. Log in to Nextcloud
2. Go to **Settings** → **Security**
3. Create a new app password in **Devices & sessions**
:::

### Nutstore Configuration Example

```bash
file_storage=webdav
webdav_url=https://dav.jianguoyun.com/dav/
webdav_username=your_email@example.com
webdav_password=your_app_password
webdav_root_path=FileCodeBox
```

::: tip Nutstore App Password
Nutstore requires an app password:
1. Log in to Nutstore web version
2. Go to **Account Info** → **Security Options**
3. Add an app password
:::

## OpenDAL Storage

OpenDAL is a unified data access layer that supports multiple storage services. Through OpenDAL, you can use Google Cloud Storage, Azure Blob Storage, and more.

### Configuration Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_storage` | string | Set to `opendal` |
| `opendal_scheme` | string | Storage service type (e.g., `gcs`, `azblob`) |
| `opendal_<scheme>_<setting>` | string | Service-specific configuration parameters |

### Install Dependencies

```bash
pip install opendal
```

### Google Cloud Storage Configuration Example

```bash
file_storage=opendal
opendal_scheme=gcs
opendal_gcs_root=/filecodebox
opendal_gcs_bucket=your-bucket-name
opendal_gcs_credential=base64_encoded_credential
```

### Azure Blob Storage Configuration Example

```bash
file_storage=opendal
opendal_scheme=azblob
opendal_azblob_root=/filecodebox
opendal_azblob_container=your-container
opendal_azblob_account_name=your_account
opendal_azblob_account_key=your_key
```

### Supported Services

OpenDAL supports numerous storage services. For the complete list, see the [OpenDAL Official Documentation](https://opendal.apache.org/docs/rust/opendal/services/index.html).

Common services include:
- `gcs` - Google Cloud Storage
- `azblob` - Azure Blob Storage
- `obs` - Huawei Cloud OBS
- `oss` - Aliyun OSS (via OpenDAL)
- `cos` - Tencent Cloud COS (via OpenDAL)
- `hdfs` - Hadoop HDFS
- `ftp` - FTP server
- `sftp` - SFTP server

::: warning OpenDAL Notes
1. Services integrated via OpenDAL download through server proxy, consuming both storage service and server bandwidth
2. Compared to native S3/OneDrive support, OpenDAL may lack some debugging information
3. OpenDAL is written in Rust with good performance
:::

## Storage Selection Recommendations

| Scenario | Recommended Storage | Reason |
|----------|---------------------|--------|
| Personal/Small deployment | Local storage | Simple and easy, no extra configuration needed |
| Enterprise intranet | MinIO + S3 | Self-hosted object storage, data control |
| Public cloud deployment | Corresponding cloud provider S3 | Fast same-region access, low cost |
| Existing OneDrive | OneDrive | Utilize existing resources |
| Existing WebDAV | WebDAV | Good compatibility |
| Special storage needs | OpenDAL | Supports more storage services |

## Common Issues

### S3 Upload Failure

1. Check if Access Key and Secret Key are correct
2. Confirm bucket name and region configuration are correct
3. Check bucket access permission settings
4. Confirm signature version (`s3v2` or `s3v4`) matches service provider requirements

### OneDrive Authentication Failure

1. Confirm using a work/school account, not a personal account
2. Check if Azure app has been granted admin consent
3. Confirm API permissions are fully configured
4. Verify username and password are correct

### WebDAV Connection Failure

1. Check if WebDAV URL format is correct
2. Confirm username and password (or app password) are correct
3. Check if server supports WebDAV protocol
4. Confirm network connection is normal
