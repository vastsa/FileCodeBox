<div align="center">

<img src="https://fastly.jsdelivr.net/gh/vastsa/FileCodeBox@V1.6/static/banners/img_1.png" alt="FileCodeBox Logo">

<p><em>Share text and files anonymously with a passcode, like picking up a package</em></p>

[![GitHub stars](https://img.shields.io/github/stars/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/network)
[![GitHub issues](https://img.shields.io/github/issues/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/issues)
[![GitHub license](https://img.shields.io/github/license/vastsa/FileCodeBox)](https://github.com/vastsa/FileCodeBox/blob/master/LICENSE)
[![QQ Group](https://img.shields.io/badge/QQ%20Group-739673698-blue.svg)](https://qm.qq.com/q/PemPzhdEIM)
[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.68+-green.svg)](https://fastapi.tiangolo.com)
[![Vue Version](https://img.shields.io/badge/Vue.js-3.x-brightgreen.svg)](https://v3.vuejs.org)

</div>

## 📝 Introduction

FileCodeBox is a lightweight file sharing tool developed with FastAPI + Vue3. It allows users to share text and files easily, where recipients only need a passcode to retrieve the files, just like picking up a package from a delivery locker.

## 🖼️ Preview

<div align="center">
<h3>
<a href="https://github.com/vastsa/FileCodeBoxFronted" target="_blank">
<img src="https://img.shields.io/badge/Frontend-FileCodeBoxFronted-blue?style=for-the-badge&logo=github" alt="Frontend Repository">
</a>
&nbsp;&nbsp;&nbsp;
<a href="https://share.lanol.cn" target="_blank">
<img src="https://img.shields.io/badge/Demo-share.lanol.cn-green?style=for-the-badge&logo=internet-explorer" alt="Demo Site">
</a>
</h3>
</div>


## 🎯 Use Cases

<table>
<tr>
<td align="center">
<h4>📁 Temporary File Sharing</h4>
Quick file sharing without registration
</td>
<td align="center">
<h4>📝 Quick Text Sharing</h4>
Share code snippets and text content
</td>
<td align="center">
<h4>🕶️ Anonymous Transfer</h4>
Privacy-protected file transfer
</td>
</tr>
<tr>
<td align="center">
<h4>💾 Temporary Storage</h4>
File storage with expiration time
</td>
<td align="center">
<h4>🔄 Cross-platform Transfer</h4>
Quick file transfer between devices
</td>
<td align="center">
<h4>🌐 Private Share Service</h4>
Build your own file sharing service
</td>
</tr>
</table>

## ✨ Core Features

<table>
<tr>
<td align="center">
<h4>🚀 Lightweight</h4>
Based on FastAPI + SQLite3 + Vue3 + ElementUI
</td>
<td align="center">
<h4>📤 Easy Upload</h4>
Support copy-paste and drag-drop
</td>
<td align="center">
<h4>📦 Multiple Types</h4>
Support text and various file types
</td>
</tr>
<tr>
<td align="center">
<h4>🔒 Security</h4>

- IP upload limits
- Error attempt limits
- File expiration
</td>
<td align="center">
<h4>🎫 Passcode Sharing</h4>
Random codes with customizable limits
</td>
<td align="center">
<h4>🌍 Multi-language</h4>
Support for Simplified Chinese, Traditional Chinese, and English
</td>
</tr>
<tr>
<td align="center">
<h4>🎭 Anonymous</h4>
No registration required
</td>
<td align="center">
<h4>🛠 Admin Panel</h4>
File and system management
</td>
<td align="center">
<h4>🐳 Docker</h4>
One-click deployment
</td>
</tr>
<tr>
<td align="center">
<h4>💾 Storage Options</h4>
Local, S3, OneDrive support
</td>
<td align="center">
<h4>📱 Responsive</h4>
Mobile-friendly design
</td>
<td align="center">
<h4>💻 CLI Support</h4>
Command-line download
</td>
</tr>
</table>

## 🚀 Quick Start

### Docker Deployment

```bash
docker run -d --restart=always -p 12345:12345 -v /opt/FileCodeBox/:/app/data --name filecodebox lanol/filecodebox:beta
```

### Manual Deployment

1. Clone the repository
```bash
git clone https://github.com/vastsa/FileCodeBox.git
```

2. Install dependencies
```bash
cd FileCodeBox
pip install -r requirements.txt
```

3. Start the service
```bash
python main.py
```

## 📖 Usage Guide

### Share Files
1. Open the website, click "Share File"
2. Select or drag files
3. Set expiration time and count
4. Get the passcode

### Retrieve Files
1. Open the website, enter passcode
2. Click retrieve
3. Download file or view text

### Admin Panel
1. Visit `/admin`
2. Enter admin password
3. Manage files and settings

## 🛠 Development Guide

### Project Structure
```
FileCodeBox/
├── apps/           # Application code
│   ├── admin/     # Admin backend
│   └── base/      # Base functions
├── core/          # Core functions
├── data/          # Data directory
└── fcb-fronted/   # Frontend code
```

### Development Environment
- Python 3.8+
- Node.js 14+
- Vue 3
- FastAPI

### Local Development
1. Backend development
```bash
python main.py
```

2. Frontend development
```bash
cd fcb-fronted
npm install
npm run dev
```

## 🤝 Contributing

1. Fork the project
2. Create your feature branch `git checkout -b feature/xxx`
3. Commit your changes `git commit -m 'Add xxx'`
4. Push to the branch `git push origin feature/xxx`
5. Open a Pull Request

## ❓ FAQ

### Q: How to modify upload size limit?
A: Change `uploadSize` in admin panel

### Q: How to configure storage engine?
A: Select storage engine and configure parameters in admin panel

### Q: How to backup data?
A: Backup the `data` directory

For more questions, visit [Wiki](https://github.com/vastsa/FileCodeBox/wiki/常见问题)

## 😀 Project Statistics and Analytics

<div align="center">
<a href="https://hellogithub.com/repository/75ad7ffedd404a6485b4d621ec5b47e6" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=75ad7ffedd404a6485b4d621ec5b47e6&claim_uid=beSz6INEkCM4mDH" alt="Featured｜HelloGitHub" style="width: 200px; height: 45px;" width="200" height="45" /></a>

![Repobeats](https://repobeats.axiom.co/api/embed/7a6c92f1d96ee57e6fb67f0df371528397b0c9ac.svg)

[![Star History](https://api.star-history.com/svg?repos=vastsa/FileCodeBox&type=Date)](https://star-history.com/#vastsa/FileCodeBox&Date)
</div>

## 📜 Disclaimer

This project is open-source for learning purposes only. It should not be used for any illegal purposes. The author is not responsible for any consequences. Please retain the project address and copyright information when using it.