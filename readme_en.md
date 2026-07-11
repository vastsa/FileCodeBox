<div align="center">

# FileCodeBox

### Anonymous File & Text Sharing with Passcode

<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/static/banners/img_1.png" alt="FileCodeBox Logo" width="400">

Share files like picking up a package — no registration required, just enter the passcode

[![GitHub stars](https://img.shields.io/github/stars/vastsa/FileCodeBox?style=flat-square&logo=github)](https://github.com/vastsa/FileCodeBox/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/vastsa/FileCodeBox?style=flat-square&logo=github)](https://github.com/vastsa/FileCodeBox/network)
[![GitHub issues](https://img.shields.io/github/issues/vastsa/FileCodeBox?style=flat-square&logo=github)](https://github.com/vastsa/FileCodeBox/issues)
[![GitHub license](https://img.shields.io/github/license/vastsa/FileCodeBox?style=flat-square)](https://github.com/vastsa/FileCodeBox/blob/master/LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/lanol/filecodebox?style=flat-square&logo=docker)](https://hub.docker.com/r/lanol/filecodebox)

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Vue.js](https://img.shields.io/badge/Vue.js-3.x-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org)

[简体中文](./README.md) | [Live Demo](https://share.lanol.cn) | [Documentation](https://github.com/vastsa/FileCodeBox/wiki/Deployment-Guide) | [FAQ](https://github.com/vastsa/FileCodeBox/wiki/FAQ)

```bash
# 🚀 Quick Deploy
docker run -d -p 12345:12345 -v /opt/FileCodeBox:/app/data --name filecodebox lanol/filecodebox:latest
# China Mirror (if slow): docker.cnb.cool/aixk/filecodebox
```

</div>

---

## Table of Contents

- [Introduction](#-introduction)
- [Features](#-features)
- [Screenshots](#-screenshots)
- [Quick Start](#-quick-start)
- [Usage Guide](#-usage-guide)
- [Development](#-development)
- [FAQ](#-faq)
- [Contributing](#-contributing)
- [Statistics](#-statistics)
- [Disclaimer](#-disclaimer)

---

## 📝 Introduction

FileCodeBox is a lightweight file sharing tool built with **FastAPI + Vue3**. Users can anonymously share text and files, and recipients only need to enter a passcode to retrieve the content — just like picking up a package from a locker.

### Use Cases

| Scenario | Description |
|----------|-------------|
| 📁 **Temporary File Sharing** | Quick file sharing without registration |
| 📝 **Code Snippet Sharing** | Share code, config files, and text content |
| 🕶️ **Anonymous Transfer** | Privacy-protected peer-to-peer transfer |
| 🔄 **Cross-Device Transfer** | Quickly sync files between devices |
| 💾 **Temporary Storage** | Cloud storage with custom expiration |
| 🌐 **Private Service** | Build your own enterprise or personal sharing service |

---

## ✨ Features

<table>
<tr>
<td width="33%" valign="top">

### 🚀 Lightweight & Fast
- FastAPI + SQLite3 backend
- Vue3 + Element Plus frontend
- One-click Docker deployment
- Minimal resource usage

</td>
<td width="33%" valign="top">

### 🔒 Secure & Reliable
- IP upload rate limiting
- Passcode attempt limiting
- Auto file expiration cleanup
- Admin authentication support

</td>
<td width="33%" valign="top">

### 📤 Easy Upload
- Drag & drop upload
- Copy & paste upload
- Command line curl upload
- Batch file upload

</td>
</tr>
<tr>
<td width="33%" valign="top">

### 🎫 Flexible Sharing
- Random / custom passcodes
- Set expiration (time/count)
- Permanent validity support
- Unified text & file management

</td>
<td width="33%" valign="top">

### 💾 Multiple Storage
- Local file system
- S3-compatible storage
- [OneDrive](./docs/guide/storage-onedrive.md)
- [OpenDAL](./docs/guide/storage-opendal.md)

</td>
<td width="33%" valign="top">

### 🌍 Internationalization
- Simplified Chinese
- Traditional Chinese
- English
- Responsive design / Dark mode

</td>
</tr>
</table>

---

## 🖼️ Screenshots

> Frontend repositories: [2024 Theme](https://github.com/vastsa/FileCodeBoxFronted) | [2023 Theme](https://github.com/vastsa/FileCodeBoxFronted2023)

<details open>
<summary><b>🎨 New Interface (2024)</b></summary>
<br>
<div align="center">
<table>
<tr>
<td><img src="./.github/images/img_7.png" alt="File Upload"></td>
<td><img src="./.github/images/img_8.png" alt="Text Share"></td>
</tr>
<tr>
<td><img src="./.github/images/img_10.png" alt="File Management"></td>
<td><img src="./.github/images/img_9.png" alt="System Settings"></td>
</tr>
<tr>
<td><img src="./.github/images/img_11.png" alt="Mobile View"></td>
<td><img src="./.github/images/img_12.png" alt="Dark Mode"></td>
</tr>
</table>
</div>
</details>

<details>
<summary><b>📦 Classic Interface (2023)</b></summary>
<br>
<div align="center">
<table>
<tr>
<td><img src="./.github/images/img.png" alt="Home"></td>
<td><img src="./.github/images/img_1.png" alt="Upload"></td>
</tr>
<tr>
<td><img src="./.github/images/img_2.png" alt="Management"></td>
<td><img src="./.github/images/img_3.png" alt="Settings"></td>
</tr>
</table>
</div>
</details>

---

## 🚀 Quick Start

### Docker Deployment (Recommended)

Pin a version tag (for example, `2.4.0`) in production for reproducible
deployments and rollbacks. `latest` moves only on formal releases; `edge-*`
identifies development images built from master.

**Option 1: Docker CLI**

```bash
# Docker Hub (Recommended)
docker run -d --restart always -p 12345:12345 -v /opt/FileCodeBox:/app/data --name filecodebox lanol/filecodebox:2.5.0 # x-release-please-version

# China Mirror (if Docker Hub is slow)
docker run -d --restart always -p 12345:12345 -v /opt/FileCodeBox:/app/data --name filecodebox docker.cnb.cool/aixk/filecodebox
```

**Option 2: Docker Compose**

```yaml
services:
  filecodebox:
    image: lanol/filecodebox:2.5.0 # x-release-please-version
    container_name: filecodebox
    restart: unless-stopped
    ports:
      - "12345:12345"
    volumes:
      - ./data:/app/data
    environment:
      - WORKERS=4
      - LOG_LEVEL=info
```

```bash
docker compose up -d
```

**Environment Variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `::` | Listen address (supports IPv4/IPv6 dual-stack) |
| `PORT` | `12345` | Service port |
| `WORKERS` | `4` | Worker processes (recommended: CPU cores) |
| `LOG_LEVEL` | `info` | Log level: `debug` / `info` / `warning` / `error` |

### Reverse Proxy Configuration

When using Nginx, add the following configuration to properly obtain client IP:

```nginx
location / {
    proxy_pass http://127.0.0.1:12345;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 100m;  # Adjust upload size limit as needed
}
```

### Manual Deployment

```bash
# 1. Clone the repository
git clone https://github.com/vastsa/FileCodeBox.git
cd FileCodeBox

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the service
python main.py
```

---

## 📖 Usage Guide

### Basic Operations

| Operation | Steps |
|-----------|-------|
| **Share File** | Open website → Select/drag files → Set expiration → Get passcode |
| **Retrieve File** | Open website → Enter passcode → Download file or view text |
| **Admin Panel** | Complete first-run setup → Visit `/#/admin` → Enter the password set during setup |

### Command Line Usage (curl)

<details>
<summary><b>Click to expand curl examples</b></summary>

**Upload File**

```bash
# Basic upload (default 1 day expiration)
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt"

# Set 1 hour expiration
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt" \
  -F "expire_value=1" \
  -F "expire_style=hour"

# Set expiration after 10 downloads
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt" \
  -F "expire_value=10" \
  -F "expire_style=count"
```

**Share Text**

```bash
curl -X POST "http://localhost:12345/share/text/" \
  -F "text=Text content to share"
```

**Download File**

```bash
curl -L "http://localhost:12345/share/select/?code=PASSCODE" -o filename
```

**Expiration Parameters**

| `expire_style` | Description |
|----------------|-------------|
| `day` | Days |
| `hour` | Hours |
| `minute` | Minutes |
| `count` | Download count |
| `forever` | Never expire |

**Response Example**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abcd1234",
    "name": "file.txt"
  }
}
```

**When Authentication Required** (after admin disables guest upload)

```bash
# 1. Get token
curl -X POST "http://localhost:12345/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"password": "<admin-password-set-during-setup>"}'

# 2. Upload with token
curl -X POST "http://localhost:12345/share/file/" \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/file.txt"
```

</details>

---

## 🛠 Development

### Project Structure

```
FileCodeBox/
├── apps/              # Application modules
│   ├── admin/         # Admin backend
│   └── base/          # Base functionality
├── core/              # Core modules
├── data/              # Data directory (generated at runtime)
├── docs/              # Documentation
└── main.py            # Entry point
```

### Local Development

**Backend**

```bash
pip install -r requirements.txt
python main.py
```

**Frontend**

```bash
# Frontend repo: https://github.com/vastsa/FileCodeBoxFronted
cd fcb-fronted
npm install
npm run dev
```

### Tech Stack

| Category | Technology |
|----------|------------|
| **Backend Framework** | FastAPI 0.128+ / Uvicorn |
| **Database** | SQLite + Tortoise ORM |
| **Data Validation** | Pydantic 2.x |
| **Async Support** | aiofiles / aiohttp / aioboto3 |
| **Object Storage** | S3 Protocol / OneDrive / OpenDAL |
| **Frontend Framework** | Vue 3 + Element Plus + Vite |
| **Runtime** | Python 3.8+ / Node.js 18+ |
| **Containerization** | Docker / Docker Compose |

---

## ❓ FAQ

<details>
<summary><b>How to modify upload size limit?</b></summary>

Modify the `uploadSize` configuration in the admin panel. If using Nginx reverse proxy, also modify `client_max_body_size`.
</details>

<details>
<summary><b>How to configure storage engine?</b></summary>

Select the storage engine type and configure parameters in the admin panel. Supports local storage, S3, OneDrive, OpenDAL, etc.
</details>

<details>
<summary><b>How to backup data?</b></summary>

Backup the `data` directory, which contains the database and uploaded files.
</details>

<details>
<summary><b>How to change admin password?</b></summary>

After logging into the admin panel, modify the `adminPassword` configuration in system settings.
</details>

For more questions, visit [Wiki](https://github.com/vastsa/FileCodeBox/wiki/FAQ)

---

## 🤝 Contributing

Issues and Pull Requests are welcome!

```bash
# 1. Fork and clone
git clone https://github.com/your-username/FileCodeBox.git

# 2. Create branch
git checkout -b feature/your-feature

# 3. Commit changes
git commit -m "feat: add your feature"

# 4. Push and create PR
git push origin feature/your-feature
```

---

## 📊 Statistics

<div align="center">

<a href="https://hellogithub.com/repository/75ad7ffedd404a6485b4d621ec5b47e6" target="_blank">
  <img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=75ad7ffedd404a6485b4d621ec5b47e6&claim_uid=beSz6INEkCM4mDH" alt="HelloGitHub" width="200">
</a>

![Repobeats](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg)

[![Star History](https://api.star-history.com/svg?repos=vastsa/FileCodeBox&type=Date)](https://star-history.com/#vastsa/FileCodeBox&Date)

</div>

---

## 🗓 Roadmap

- [ ] 2025 New Theme
- [ ] File Collection Feature

---

## 📜 Disclaimer

This project is open-source for learning and communication purposes only. It should not be used for any illegal purposes. The author is not responsible for any consequences. Please retain the project address and copyright information when using it.

---

<div align="center">

**If you find this project helpful, please give it a ⭐ Star!**

Made with ❤️ by [vastsa](https://github.com/vastsa)

</div>
