# Getting Started

## Introduction

FileCodeBox is a simple and efficient file sharing tool that supports temporary file transfer, sharing, and management. This guide will help you quickly deploy and use FileCodeBox.

## Features

- 🚀 Quick Deployment: Support Docker one-click deployment
- 🔒 Secure & Reliable: File access requires extraction code
- ⏱️ Time Control: Support setting file expiration time
- 📊 Download Limit: Can limit file download times
- 🖼️ File Preview: Support preview of images, videos, audio, and other formats
- 📱 Responsive Design: Perfect adaptation for mobile and desktop

## Deployment Methods

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

## Usage

1. Access the System
   Open browser and visit `http://localhost:12345`

2. Upload Files
   - Click upload button or drag files to upload area
   - Set file expiration time and download limit
   - Get share link and extraction code

3. Download Files
   - Visit share link
   - Enter extraction code
   - Download file

4. Admin Panel
   - Visit `http://localhost:12345/#/admin`
   - Enter admin password: `FileCodeBox2023`
   - Enter admin panel
   - View system information, file list, user management, etc.

## Next Steps

- [Storage Configuration](/en/guide/storage) - Learn how to configure different storage methods
- [Security Settings](/en/guide/security) - Learn how to enhance system security
- [API Documentation](/en/api/) - Learn how to integrate through API 