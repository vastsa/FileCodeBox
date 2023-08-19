# OneDrive作为存储的配置方法

**仅支持工作或学校账户，并且需要有管理员权限以授权API**

## 1. 需要配置的参数

```
file_storage=onedrive
onedrive_domain=XXXXXX
onedrive_client_id=XXXXXX-XXXXXX-XXXXXX-XXXXXX
onedrive_username=XXXXXX@XXXXXX
onedrive_password=XXXXXX
```

`onedrive_username`和`onedrive_password`是你的账户名（邮箱）和密码，另外两个参数需要在[微软Azure门户](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)中注册应用后获取。

## 2. 应用注册

1. 登录[https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)，鼠标置于右上角账号处，浮窗将显示的`域`即为`onedrive_domain`的值。
![onedrive_domain](https://api.onedrive.com/v1.0/shares/s!Au-BDzXcM6_VmGCiErO85doq9Tcu/root/content)

2. 点击左上角的`+新注册`，输入名称，
  * 受支持的帐户类型：选择任何组织目录(任何 Azure AD 目录 - 多租户)中的帐户和个人 Microsoft 帐户(例如，Skype、Xbox)
  * 重定向 URI (可选)：选择`Web`，并输入`http://localhost`

3. 完成注册后进入概述页面，在概要中找到`应用程序(客户端)ID`，即为`onedrive_client_id`的值。
![onedrive_client_id](https://api.onedrive.com/v1.0/shares/s!Au-BDzXcM6_VmGHD4CNyJxm_QBb8/root/content)

4. 此时还需要配置允许公共客户端流和API权限
  * 在左侧选择`身份验证`，找到`允许的客户端流`，选择`是`，并**点击`保存`**。
  ![允许的客户端流](https://api.onedrive.com/v1.0/shares/s!Au-BDzXcM6_VmGJQMOlOCb2-L0Lh/root/content)
  * 在左侧选择`API权限`，点击`+添加权限`，选择`Microsoft Graph`->`委托的权限`，并勾选下述权限：openid、Files中所有权限、User.Read，如下图所示。最后**点击下方的`添加权限`**。
  ![添加权限](https://api.onedrive.com/v1.0/shares/s!Au-BDzXcM6_VmGOZzz7sIrdXkD4w/root/content)
  * 最后点击`授予管理员同意`，并**点击`是`**，最终状态变为`已授予`。
  ![授予管理员同意](https://api.onedrive.com/v1.0/shares/s!Au-BDzXcM6_VmGSOAnjnHUlbirbU/root/content)

## 3. 使用下述代码测试是否配置成功

安装依赖：`pip install Office365-REST-Python-Client`

```python
# common.py
import msal
domain = 'XXXXXX'
client_id = 'XXXXXX'
username = 'XXXXXX'
password = 'XXXXXX'

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
```

测试登录，如果成功打印出账户名，说明配置成功。

```python
from common import acquire_token_pwd

from office365.graph_client import GraphClient
try:
    client = GraphClient(acquire_token_pwd)
    me = client.me.get().execute_query()
    print(me.user_principal_name)
except Exception as e:
    print(e)
```

测试文件上传

```python
import os
from office365.graph_client import GraphClient
from common import acquire_token_pwd

remote_path = 'tmp'
local_path = '.tmp/1689843925000.png'

def convert_link_to_download_link(link):
    import re
    p1 = re.search(r'https:\/\/(.+)\.sharepoint\.com', link).group(1)
    p2 = re.search(r'personal\/(.+)\/', link).group(1)
    p3 = re.search(rf'{p2}\/(.+)', link).group(1)
    return f'https://{p1}.sharepoint.com/personal/{p2}/_layouts/52/download.aspx?share={p3}'

client = GraphClient(acquire_token_pwd)
folder = client.me.drive.root.get_by_path(remote_path)
# 1. upload
file = folder.upload_file(local_path).execute_query()
print(f'File {file.web_url} has been uploaded')
# 2. create sharing link
remote_file = folder.get_by_path(os.path.basename(local_path))
permission = remote_file.create_link("view", "anonymous").execute_query()
print(f"sharing link: {convert_link_to_download_link(permission.link.webUrl)}")
```

测试文件下载

```python
import os
from office365.graph_client import GraphClient
from common import acquire_token_pwd

remote_path = 'tmp/1689843925000.png'
local_path = '.tmp'
if not os.path.exists(local_path):
    os.makedirs(local_path)

client = GraphClient(acquire_token_pwd)
remote_file = client.me.drive.root.get_by_path(remote_path).get().execute_query()
with open(os.path.join(local_path, os.path.basename(remote_path)), 'wb') as local_file:
    remote_file.download(local_file).execute_query()
    print(f'{remote_file.name} has been downloaded into {local_file.name}')
```

测试删除文件

```python
from office365.graph_client import GraphClient
from common import acquire_token_pwd

remote_path = 'tmp/1689843925000.png'

client = GraphClient(acquire_token_pwd)
file = client.me.drive.root.get_by_path(remote_path)
file.delete_object().execute_query()
```
