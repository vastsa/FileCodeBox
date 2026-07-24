---
layout: home

hero:
  name: "FileCodeBox"
  text: "Share files like picking up a package"
  tagline: A lightweight, modern, self-hosted service for files and text
  image:
    src: /logo_small.png
    alt: FileCodeBox
  actions:
    - theme: brand
      text: Get Started
      link: /en/guide/getting-started
    - theme: alt
      text: Live Demo
      link: https://share.lanol.cn
    - theme: alt
      text: Deployment Guide
      link: /en/guide/getting-started#docker-deployment-recommended

features:
  - icon: 01
    title: Share instantly
    details: Files and text in one flow, with batch, chunked, and resumable uploads
  - icon: 02
    title: Flexible expiry
    details: Expire by time or retrieval count, or keep content permanently
  - icon: 03
    title: Own your data
    details: Local, S3, OneDrive, WebDAV, and OpenDAL storage
---

## Start in 30 seconds

```bash
docker run -d --restart unless-stopped \
  -p 12345:12345 \
  -v ./data:/app/data \
  --name filecodebox \
  lanol/filecodebox:2.5.4 # x-release-please-version
```

Open `http://localhost:12345` and complete the first-run setup.

<div class="doc-paths">
  <a class="doc-path" href="/en/guide/getting-started">
    <span>Get started</span>
    <strong>Deploy, initialize, and upgrade</strong>
    <small>Run FileCodeBox from a clean server →</small>
  </a>
  <a class="doc-path" href="/en/guide/storage">
    <span>Operate</span>
    <strong>Storage, configuration, and security</strong>
    <small>Choose production-ready storage and protection →</small>
  </a>
  <a class="doc-path" href="/en/api/">
    <span>Integrate</span>
    <strong>API and upload workflows</strong>
    <small>Build on sharing, chunked uploads, and administration →</small>
  </a>
</div>

## Interface preview

<p align="center">
  <img src="/screenshots/retrieve.webp" alt="Retrieve files" width="860" />
</p>

<p align="center">
  <img src="/screenshots/send.webp" alt="Send files" width="48%" />
  &nbsp;
  <img src="/screenshots/dashboard.webp" alt="Admin dashboard" width="48%" />
</p>

<table>
<tr>
<td width="33%"><img src="/screenshots/login.webp" alt="Admin login" /></td>
<td width="33%"><img src="/screenshots/files.webp" alt="File management" /></td>
<td width="33%"><img src="/screenshots/settings.webp" alt="System settings" /></td>
</tr>
</table>

::: warning Responsible use
Use FileCodeBox only for lawful file and text sharing. Operators are responsible for deployment security, data compliance, and content moderation.
:::
