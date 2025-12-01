# Google Drive Setup - Quick Guide

## 1. Get Google Credentials (5 minutes)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click **Create Project** → Name it "Bird Detection" → Create
3. Click **Enable APIs** → Search "Google Drive API" → Enable
4. Click **Create Credentials** → OAuth client ID
5. Choose **Desktop app** → Name it "Bird Detection"
6. Download → Save as `client_secret.json`

## 2. Install Credentials

Place `client_secret.json` in your project folder:
```
BirdBathPhotographyUsingOakCameraRaspPi5/
├── main.py
├── client_secret.json  ← Here
└── ...
```

## 3. Authorize

**Option A: Through the App**
1. Open Bird Detection app
2. Go to **Configuration** tab
3. Click **Setup Google Drive OAuth**
4. A terminal window opens
5. Browser opens → Sign in → Allow access
6. Done! ✅

**Option B: Manual Setup**
```bash
cd BirdBathPhotographyUsingOakCameraRaspPi5/
python3 setup_google_drive.py
```

## Notes

- First time only - authorization saves to `token.json`
- Uploads go to "Bird Photos" folder in your Drive
- Check Services tab for upload status