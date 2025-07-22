# 🔒 Security Configuration Guide

## 📋 Quick Setup (Recommended)

### 1. Use the GUI Configuration
The easiest way to configure all settings:

1. Run the app: `python3 main.py`
2. Go to **Configuration tab**
3. Enter your API keys and settings in the GUI
4. Click **Save Configuration**

The app automatically creates and manages `config.json` for you!

## ⚙️ Manual Configuration (Advanced)

If you need to edit config files directly:

#### OpenAI API Key
```json
"openai": {
    "api_key": "sk-proj-your-actual-openai-key-here",
    "enabled": true,
    "max_images_per_hour": 10
}
```

#### Gmail App Password
```json
"email": {
    "sender": "your-actual-email@gmail.com",
    "password": "your-actual-app-password",
    "receivers": {
        "primary": "your-actual-email@gmail.com"
    }
}
```

#### Update Storage Path
```json
"storage": {
    "save_dir": "/home/yourusername/BirdPhotos",
    "max_size_gb": 2,
    "cleanup_time": "23:30"
}
```

## 🛡️ Security Best Practices

### API Keys
- **OpenAI**: Get your API key from https://platform.openai.com/api-keys
- **Gmail**: Use App Password (not your regular password) from https://myaccount.google.com/apppasswords

### File Permissions
```bash
# Secure your config file
chmod 600 config.json

# Make sure only you can read it
ls -la config.json  # Should show: -rw------- 1 you you
```

### Environment Variables (Alternative)
For extra security, you can use environment variables:

```bash
# Create .env file
cat > .env << EOF
OPENAI_API_KEY=your_openai_key_here
GMAIL_APP_PASSWORD=your_app_password_here
EOF

# Secure the .env file
chmod 600 .env
```

## ⚠️ Important Security Notes

### Never Commit Secrets
- `config.json` is in `.gitignore` - keep it there!
- Never commit real API keys to public repositories
- If you accidentally commit secrets, change them immediately

### Google Drive OAuth
- OAuth2 credentials are stored in `token.pickle` after setup
- This file is automatically ignored by git
- Delete this file to re-authenticate

### Network Security
- Web interface runs on port 5000 by default
- Only expose to trusted networks
- Consider using a reverse proxy with HTTPS for remote access

### Regular Maintenance
- Rotate API keys periodically
- Monitor your API usage on service dashboards
- Check logs for any unusual activity

## 🚨 If You Accidentally Expose Secrets

1. **Change the compromised keys immediately**
2. **Revoke old keys** on the service dashboards
3. **Update your config.json** with new keys
4. **Monitor for any unauthorized usage**

## 📞 Getting Help

- OpenAI API issues: https://help.openai.com/
- Gmail App Password: https://support.google.com/accounts/answer/185833
- Google Drive API: https://developers.google.com/drive/api/guides/about-auth

Remember: Keep your credentials secure and never share them publicly! 🔐