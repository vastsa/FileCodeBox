<div align="center">

<img src="./docs/public/logo_small.png" alt="FileCodeBox" width="112" />

# FileCodeBox

**A self-hosted file locker that works out of the box**

Share files and text anonymously. No account required—just enter a passcode.

[Live Demo](https://share.lanol.cn) · [Documentation](https://fcb-docs.aiuo.net/en/) · [Quick Start](#quick-start) · [简体中文](./readme.md)

[![Release](https://img.shields.io/github/v/release/vastsa/FileCodeBox?style=for-the-badge&color=6366F1)](https://github.com/vastsa/FileCodeBox/releases/latest)
[![Docker Pulls](https://img.shields.io/docker/pulls/lanol/filecodebox?style=for-the-badge&logo=docker&color=0EA5E9)](https://hub.docker.com/r/lanol/filecodebox)
[![License](https://img.shields.io/github/license/vastsa/FileCodeBox?style=for-the-badge&color=22C55E)](./LICENSE)
[![Stars](https://img.shields.io/github/stars/vastsa/FileCodeBox?style=for-the-badge&logo=github&color=F59E0B)](https://github.com/vastsa/FileCodeBox/stargazers)

</div>

```bash
docker run -d --restart unless-stopped -p 12345:12345 -v ./data:/app/data --name filecodebox lanol/filecodebox:2.5.0 # x-release-please-version
```

<div align="center">
  <sub>Open <code>http://localhost:12345</code>, complete first-run setup, and start sharing.</sub>
</div>

<br />

<p align="center">
  <img src="./.github/images/readme/retrieve-dark.png" alt="FileCodeBox dark retrieval screen" width="880" />
</p>

## Why FileCodeBox

<table>
<tr>
<td width="33%" valign="top">

### Effortless sharing

No account system. Upload content, get a passcode, and let the recipient download the file or read the text.

</td>
<td width="33%" valign="top">

### Self-hosting first

Run everything in one Docker container. Your data and configuration stay on infrastructure you control.

</td>
<td width="33%" valign="top">

### Built for real workloads

Batch, chunked, and presigned uploads with expiration policies, capacity limits, an admin console, and multiple storage backends.

</td>
</tr>
</table>

## Highlights

| Sharing | Administration & security | Storage & delivery |
| --- | --- | --- |
| Unified file and text sharing | Secure first-run setup | Local filesystem |
| Drag, paste, and batch upload | Admin sessions and access control | S3-compatible storage |
| Random or custom passcodes | Upload and passcode rate limits | OneDrive and WebDAV |
| Time, count, or permanent expiry | Automatic cleanup and quotas | OpenDAL integrations |
| Chunked upload and resume | File and storage health views | Multi-architecture Docker images |
| Responsive UI and dark mode | Chinese and English admin UI | Reverse-proxy friendly |

## Product Preview

<table>
<tr>
<td width="50%"><img src="./.github/images/readme/send.png" alt="FileCodeBox file sharing" /></td>
<td width="50%"><img src="./.github/images/readme/dashboard.png" alt="FileCodeBox admin dashboard" /></td>
</tr>
<tr>
<td align="center"><sub>A focused flow for sending files and text</sub></td>
<td align="center"><sub>A dashboard built around file health and storage policy</sub></td>
</tr>
</table>

<details>
<summary><b>See more screens</b></summary>
<br />
<table>
<tr>
<td><img src="./.github/images/readme/files.png" alt="File management" /></td>
<td><img src="./.github/images/readme/settings.png" alt="System settings" /></td>
</tr>
<tr>
<td><img src="./.github/images/readme/login.png" alt="Admin login" /></td>
<td><img src="./.github/images/readme/mobile-files.png" alt="Mobile file management" /></td>
</tr>
</table>
</details>

<p align="center">
  <img src="./.github/images/readme/mobile-retrieve.png" alt="Mobile retrieval" width="30%" />
  &nbsp;
  <img src="./.github/images/readme/mobile-send.png" alt="Mobile sharing" width="30%" />
  &nbsp;
  <img src="./.github/images/readme/mobile-files.png" alt="Mobile admin" width="30%" />
</p>

> The active theme lives in [FileCodeBoxFronted](https://github.com/vastsa/FileCodeBoxFronted). Image builds automatically use the latest commit from its default branch.

## Quick Start

### Docker Compose

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
```

```bash
docker compose up -d
```

Pin a version in production for reliable rollbacks. `latest` tracks the newest stable release; `edge-*` identifies development images from `master`.

### Run from source

```bash
git clone https://github.com/vastsa/FileCodeBox.git
cd FileCodeBox
pip install -r requirements.txt
python main.py
```

The default URL is `http://localhost:12345`. Follow the first-run flow to create the administrator password.

### Reverse proxy

<details>
<summary><b>Nginx example</b></summary>

```nginx
location / {
    proxy_pass http://127.0.0.1:12345;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 100m;
}
```

</details>

## How It Works

| Action | Flow |
| --- | --- |
| Share files | Select or drop files → choose expiry → receive a passcode |
| Share text | Enter text → choose expiry → receive a passcode |
| Retrieve content | Enter a passcode → read text or download files |
| Manage the service | Open `/#/admin` → inspect files, metrics, and settings |

Uploads also work from the command line:

```bash
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt" \
  -F "expire_value=1" \
  -F "expire_style=day"
```

For complete API, chunk upload, and storage configuration details, see:

- [Getting Started](https://fcb-docs.aiuo.net/en/guide/getting-started)
- [Uploads and Chunks](https://fcb-docs.aiuo.net/en/guide/upload)
- [Storage](https://fcb-docs.aiuo.net/en/guide/storage)
- [Security](https://fcb-docs.aiuo.net/en/guide/security)
- [API Reference](https://fcb-docs.aiuo.net/en/api/)

## Architecture

```text
Browser / CLI
      │
      ▼
FastAPI · Uvicorn
      │
      ├── SQLite · Tortoise ORM
      ├── Local / S3 / OneDrive / WebDAV / OpenDAL
      └── Vue 3 · Vite frontend
```

| Layer | Technology |
| --- | --- |
| API | FastAPI · Pydantic · Uvicorn |
| Data | SQLite · Tortoise ORM |
| Async I/O | aiofiles · aiohttp · aioboto3 |
| Frontend | Vue 3 · TypeScript · Vite · Tailwind CSS |
| Delivery | Docker · GitHub Actions · VitePress |

## Development

```bash
# Backend
pip install -r requirements.txt
python main.py

# Tests
python -m pytest tests
```

The frontend is maintained in [FileCodeBoxFronted](https://github.com/vastsa/FileCodeBoxFronted):

```bash
pnpm install
pnpm dev
```

## FAQ

<details>
<summary><b>How do I back up or migrate the service?</b></summary>

Stop the service and back up the entire `data` directory. It contains the database, runtime configuration, and locally stored files.

</details>

<details>
<summary><b>How do I change the upload size?</b></summary>

Update the upload limit in the admin console. If you use Nginx, a CDN, or another gateway, update its request body limit as well.

</details>

<details>
<summary><b>Which storage backends are supported?</b></summary>

Local, S3, OneDrive, WebDAV, and OpenDAL are built in. See the [storage guide](https://fcb-docs.aiuo.net/en/guide/storage) for configuration details.

</details>

## Contributing

Issues, feature ideas, and pull requests are welcome. Use clear Conventional Commits when contributing code:

```text
fix: resolve file download issue
feat: add a storage adapter
```

- [Open an issue](https://github.com/vastsa/FileCodeBox/issues/new/choose)
- [Read the contribution guide](https://fcb-docs.aiuo.net/en/contributing)
- [Browse the changelog](https://fcb-docs.aiuo.net/en/changelog)

## License

FileCodeBox is released under [LGPL-3.0](./LICENSE). Use it in accordance with applicable laws and retain the project URL and copyright notice.

<div align="center">

If FileCodeBox helps you, consider leaving a [Star](https://github.com/vastsa/FileCodeBox/stargazers).

Made by [vastsa](https://github.com/vastsa)

</div>
