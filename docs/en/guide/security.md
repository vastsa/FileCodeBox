# Security Settings

FileCodeBox provides multiple layers of security mechanisms to protect your file sharing service. This document explains how to properly configure security options to ensure secure system operation.

## Admin Password

### Change Default Password

::: danger Important Security Warning
FileCodeBox's default admin password is `FileCodeBox2023`. **You must change this password immediately in production environments!** Using the default password allows anyone to access your admin panel.
:::

There are two ways to change the admin password:

**Method 1: Via Admin Panel (Recommended)**

1. Access `/admin` to enter the admin panel
2. Log in with the current password
3. Go to the "System Settings" page
4. Find the `admin_token` configuration item
5. Enter a new secure password and save

**Method 2: Via Database**

Configuration is stored in the `keyvalue` table of the `data/filecodebox.db` database. You can directly modify the `admin_token` value.

### Password Security Recommendations

- Use a strong password with at least 16 characters
- Include uppercase and lowercase letters, numbers, and special characters
- Avoid common words or personal information
- Change password regularly

```python
# Recommended password format example
"admin_token": "Xk9#mP2$vL5@nQ8&wR3"
```

### Hide Admin Entry

By default, the admin panel entry is hidden. You can control whether to show the admin entry on the homepage via the `showAdminAddr` configuration:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `showAdminAddr` | int | `0` | Show admin entry (1=show, 0=hide) |

::: tip Recommendation
For public services, it's recommended to keep `showAdminAddr` at `0` and access the admin panel directly via the `/admin` path.
:::

## IP Rate Limiting

FileCodeBox has built-in IP-based rate limiting mechanisms to effectively prevent abuse and attacks.

### Upload Rate Limiting

Limit the number of uploads from a single IP within a specified time:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `uploadMinute` | int | `1` | Upload limit time window (minutes) |
| `uploadCount` | int | `10` | Maximum uploads allowed within the time window |

**How it works:**
- System records upload requests from each IP
- When an IP's upload count reaches `uploadCount` within `uploadMinute` minutes
- Subsequent upload requests from that IP will be rejected with HTTP 423 error
- Counter resets after the time window expires

**Configuration examples:**

```python
# Relaxed configuration: Max 20 uploads in 5 minutes
{
    "uploadMinute": 5,
    "uploadCount": 20
}

# Strict configuration: Max 3 uploads in 1 minute
{
    "uploadMinute": 1,
    "uploadCount": 3
}
```


### Error Rate Limiting

Limit the number of error attempts from a single IP to prevent brute-force attacks on extraction codes:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `errorMinute` | int | `1` | Error limit time window (minutes) |
| `errorCount` | int | `1` | Maximum errors allowed within the time window |

**How it works:**
- When a user enters an incorrect extraction code, the system records the error count for that IP
- When error count reaches `errorCount`, that IP will be temporarily locked
- Lock duration is `errorMinute` minutes
- During lockout, all extraction requests from that IP will be rejected

**Configuration example:**

```python
# Anti-brute-force configuration: Max 3 errors in 5 minutes
{
    "errorMinute": 5,
    "errorCount": 3
}
```

::: warning Note
The default configuration `errorMinute=1, errorCount=1` is very strict, meaning you need to wait 1 minute after entering one incorrect extraction code before retrying. Adjust this configuration based on actual needs.
:::

## Upload Restrictions

### File Size Limit

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `uploadSize` | int | `10485760` | Maximum single file upload size (bytes), default 10MB |
| `openUpload` | int | `1` | Enable upload functionality (1=enabled, 0=disabled) |

**Common size conversions:**
- 10MB = 10 * 1024 * 1024 = `10485760`
- 50MB = 50 * 1024 * 1024 = `52428800`
- 100MB = 100 * 1024 * 1024 = `104857600`
- 1GB = 1024 * 1024 * 1024 = `1073741824`

### File Expiration Settings

Through file expiration mechanisms, you can automatically clean up expired files, reducing storage usage and security risks:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `expireStyle` | list | `["day","hour","minute","forever","count"]` | Available expiration methods |
| `max_save_seconds` | int | `0` | Maximum file retention time (seconds), 0 means no limit |

**Expiration methods explained:**
- `day` - Expire by days
- `hour` - Expire by hours
- `minute` - Expire by minutes
- `forever` - Never expire (requires alphanumeric extraction code)
- `count` - Expire by download count

**Security recommendations:**

For public services, it's recommended to:
1. Remove the `forever` option to avoid permanent file storage
2. Set `max_save_seconds` to limit maximum retention time
3. Prefer using `count` method for automatic deletion after download

```python
# Recommended configuration for public services
{
    "expireStyle": ["hour", "minute", "count"],
    "max_save_seconds": 86400  # Max retention 1 day
}
```

### Disable Upload Functionality

In some cases, you may need to temporarily disable upload functionality:

```python
{
    "openUpload": 0  # Disable upload functionality
}
```

## Reverse Proxy Security Configuration

In production environments, Nginx or other reverse proxy servers are typically used. Here are security configuration recommendations:

### Nginx Configuration Example

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Force HTTPS redirect
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL certificate configuration
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers on;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Limit request body size (match uploadSize configuration)
    client_max_body_size 100M;
    
    # Pass real IP
    location / {
        proxy_pass http://127.0.0.1:12345;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Static resource caching
    location /assets {
        proxy_pass http://127.0.0.1:12345;
        proxy_cache_valid 200 7d;
        add_header Cache-Control "public, max-age=604800";
    }
}
```

### Key Security Configuration Notes

**1. Pass Real IP**

FileCodeBox's IP limiting functionality depends on obtaining the client's real IP. The system obtains IP in the following order:
1. `X-Real-IP` request header
2. `X-Forwarded-For` request header
3. Direct client connection IP

Ensure the reverse proxy correctly sets these headers:

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

**2. Request Body Size Limit**

Nginx's `client_max_body_size` should match or be slightly larger than FileCodeBox's `uploadSize` configuration:

```nginx
client_max_body_size 100M;  # Allow max 100MB uploads
```

**3. HTTPS Encryption**

It's strongly recommended to enable HTTPS in production environments:
- Protect uploaded file content
- Protect admin login credentials
- Prevent man-in-the-middle attacks

### Caddy Configuration Example

```nginx
your-domain.com {
    reverse_proxy localhost:12345
    
    header {
        X-Frame-Options "SAMEORIGIN"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
}
```

## Security Checklist

Before deploying FileCodeBox, confirm the following security configurations:

- [ ] Changed default admin password `admin_token`
- [ ] Hidden admin entry `showAdminAddr: 0`
- [ ] Configured appropriate upload rate limiting
- [ ] Configured error rate limiting to prevent brute-force attacks
- [ ] Set reasonable file size limits
- [ ] Configured file expiration policy
- [ ] Enabled HTTPS encryption
- [ ] Reverse proxy correctly passes real IP
- [ ] Set security response headers

## Recommended Security Configurations

### Public Service Configuration

```python
{
    "admin_token": "your-very-secure-password",
    "showAdminAddr": 0,
    "uploadSize": 10485760,           # 10MB
    "uploadMinute": 1,
    "uploadCount": 5,
    "errorMinute": 5,
    "errorCount": 3,
    "expireStyle": ["hour", "minute", "count"],
    "max_save_seconds": 86400,        # Max 1 day
    "openUpload": 1
}
```

### Internal Service Configuration

```python
{
    "admin_token": "internal-secure-password",
    "showAdminAddr": 1,
    "uploadSize": 104857600,          # 100MB
    "uploadMinute": 5,
    "uploadCount": 50,
    "errorMinute": 1,
    "errorCount": 5,
    "expireStyle": ["day", "hour", "forever"],
    "max_save_seconds": 0,            # No limit
    "openUpload": 1
}
```

## Next Steps

- [Configuration Guide](/en/guide/configuration) - Learn about all configuration options
- [Storage Configuration](/en/guide/storage) - Configure secure storage backends
- [File Sharing](/en/guide/share) - Learn about file sharing features
