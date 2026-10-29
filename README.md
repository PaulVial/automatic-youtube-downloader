# automatic-youtube-downloader

Every day, this script checks one or more YouTube playlists, downloads the tracks it hasn't fetched yet as
**320 kbps MP3** files, and drops them into a folder in your **Google Drive**.

- Files are named `Artist - Title.mp3`. Clutter like "(Official Video)" is removed, while "(Extended Mix)",
  "(X Remix)" and similar are kept.
- ID3 tags (artist, title) and a square cover, readable by Rekordbox, Serato and Traktor.
- The first run fetches the whole playlist. After that, only new additions.
- It runs on its own on Google Cloud. Your computer doesn't need to be on.

> Personal use only. Downloading from YouTube is not allowed by its terms of service: what you do with the files
> is up to you. Support the artists (Bandcamp, Beatport…).

## How much does it cost?

**€0 in practice**: everything stays within the Google Cloud free tier (one run a day, a few minutes each).
Google still asks for a credit card to activate the project. Set a €1 budget alert (step 1) and you'll be warned
about any charge, however small.

The only limit: a free Google Drive has 15 GB, which is about 1,000 tracks.

## How it works

```
Cloud Scheduler (daily)
        │
        ▼
Cloud Run Job ── reads the playlists ──► YouTube
        │        downloads + converts to MP3
        │
        ├── remembers tracks already done ──► Cloud Storage (state.json)
        └── uploads the MP3s ───────────────► Google Drive
```

---

## Setup (about 30 min, one time only)

### What you need

- A Google account (Gmail is fine) and a credit card.
- **Python 3.10+**, for step 4 only.
- **Google Cloud CLI** (`gcloud`): https://cloud.google.com/sdk/docs/install
- A **bash** terminal: Terminal on Mac/Linux, **Git Bash** or WSL on Windows.

> Don't want to install gcloud? You can do steps 5 and 6 in [Cloud Shell](https://shell.cloud.google.com), a
> terminal in your browser with everything already installed. Just upload the project folder along with your
> `config.env` and `token.json`.

### 1. Create the Google Cloud project

1. Go to https://console.cloud.google.com/projectcreate and create a project, for example `dj-downloader`.
   Write down its **ID** (shown under the name, for example `dj-downloader-123456`).
2. Link a billing account: https://console.cloud.google.com/billing/linkedaccount
3. *(Recommended)* Create a €1 budget alert: **Billing → Budgets & alerts → Create budget**.
4. In your terminal:
   ```bash
   gcloud auth login your.address@gmail.com
   gcloud services enable drive.googleapis.com --project=YOUR_PROJECT_ID --account=your.address@gmail.com
   ```
   If you have several Google accounts in gcloud (personal and work, for example), put the right one in
   `GCLOUD_ACCOUNT` in step 2. The deploy script will use it without changing your gcloud configuration.

### 2. Get the code and configure it

```bash
git clone https://github.com/PaulVial/automatic-youtube-downloader.git
cd automatic-youtube-downloader
cp config.example.env config.env
```

Open `config.env` and fill in at least:

```
PROJECT_ID=dj-downloader-123456
PLAYLISTS=https://www.youtube.com/playlist?list=PLxxxx,https://www.youtube.com/playlist?list=PLyyyy
```

Playlists must be **public** or **unlisted**. The other options (Drive folder name, run time…) are explained in
the file.

### 3. Allow access to Google Drive

The script needs your permission to put files in your Drive. To do that, you create a private "OAuth app" that
only you use.

In the console, open **Google Auth Platform**: https://console.cloud.google.com/auth/overview

1. **Get started**: app name `automatic-youtube-downloader`, your email address. Audience type: **External**.
2. **Branding**: Google requires these fields before you can switch to Production. Since the app only uses a
   "non-sensitive" permission, Google doesn't review the pages: they just need to exist.

   | Field | Value |
   |---|---|
   | Application home page | `https://github.com/PaulVial/automatic-youtube-downloader` |
   | Application privacy policy link | `https://github.com/PaulVial/automatic-youtube-downloader/blob/main/PRIVACY.md` |
   | Authorized domains | `github.com` |
   | User support email / Developer contact information | your email address |

   The GitHub repo must be **public** for these links to work. If you'd rather not publish your copy of the code,
   paste the content of [PRIVACY.md](PRIVACY.md) into a [public Gist](https://gist.github.com) and use the Gist
   URL for both fields.

3. **Audience**: click **Publish app** to switch it to **Production**.
   ⚠️ Don't skip this: in "Testing" mode, the authorization expires after 7 days and the script stops working.
4. **Clients → Create client**: type **Desktop app**, then **Download JSON**. Rename the file to
   `client_secret.json` and put it in the project folder.

### 4. Generate the Drive token

```bash
pip install google-auth-oauthlib
python scripts/get_drive_token.py client_secret.json
```

A browser opens: sign in with the Google account **whose Drive you want to use**. If Google shows "Google hasn't
verified this app", click **Advanced → Go to automatic-youtube-downloader**. That's expected: it's your own app.

The script creates `token.json`. **This file gives access to your Drive: don't share it.**

> The app only sees files it created itself (`drive.file` permission): it has no access to the rest of your
> Drive. That's also why the destination folder is created by the script and can't be a folder that already
> exists. Once it's created, you can move it anywhere in your Drive.

### 5. *(Optional)* Test on your computer

Requires Docker. See what would be downloaded, without downloading anything:

```bash
docker build -t automatic-youtube-downloader .
docker run --rm --env-file config.env automatic-youtube-downloader --dry-run
```

Download 1 track for real into your Drive:

Mac / Linux:

```bash
docker run --rm --env-file config.env \
  -e STATE_URI=/data/state.json -e DRIVE_TOKEN_FILE=/data/token.json \
  -v "$(pwd):/data" automatic-youtube-downloader --limit 1
```

Windows (PowerShell):

```powershell
docker run --rm --env-file config.env -e STATE_URI=/data/state.json -e DRIVE_TOKEN_FILE=/data/token.json -v "${PWD}:/data" automatic-youtube-downloader --limit 1
```

Windows (Git Bash): use the Mac / Linux command with `MSYS_NO_PATHCONV=1 ` in front of it.

No risk of duplicates later: before downloading a track, the script checks whether it's already in the Drive.

### 6. Deploy to Google Cloud

```bash
bash deploy/deploy.sh
```

Takes about 5 minutes. The script creates everything it needs and is safe to run again.

Then start a first run right away, instead of waiting for the next scheduled one:

```bash
gcloud run jobs execute automatic-youtube-downloader --region=europe-west1
```

The first run fetches the whole playlist: expect about 20 seconds per track. The folder (**DJ - YouTube** by
default) appears in your Drive.

---

## Day to day

| I want to… | I do… |
|---|---|
| Add or remove a playlist | Edit `PLAYLISTS` in `config.env`, then `bash deploy/deploy.sh` |
| Change the run time | Edit `SCHEDULE` in `config.env`, then `bash deploy/deploy.sh` |
| Start a run now | `gcloud run jobs execute automatic-youtube-downloader --region=europe-west1` |
| See the logs | Console → **Cloud Run → Jobs → automatic-youtube-downloader → Executions** |
| Update yt-dlp (if YouTube breaks something) | `bash deploy/deploy.sh` (the image is rebuilt with the latest version) |

A track that has been downloaded is never downloaded again, even if you delete it from the Drive. So you can
empty the Drive folder as you move tracks into your DJ library.

## Troubleshooting

**"Sign in to confirm you're not a bot" in the logs**
YouTube sometimes blocks Google Cloud servers. The run stops cleanly and resumes the next day. If it keeps
happening, there are two fixes:

1. **YouTube cookies** (free). Preferably use a secondary Google account, since YouTube might flag it.
   1. Open a private browsing window and sign in to YouTube.
   2. With the *Get cookies.txt LOCALLY* extension, export the youtube.com cookies to `cookies.txt` at the root
      of the project.
   3. Close the private window, then run `bash deploy/deploy.sh` again.
2. **Residential proxy** (paid, a few € per GB, and a track is about 5 MB): set `PROXY_URL` in `config.env`, then
   run `bash deploy/deploy.sh` again.

**"Token Google Drive refusé" (Drive token rejected)**
The OAuth app most likely stayed in "Testing" mode (see step 3.3). Switch it to Production, redo step 4, then run
`bash deploy/deploy.sh` again.

**A track has the wrong name**
The name comes from the YouTube title. Rename the file by hand in the Drive: the script won't touch it again.

**A track fails every time** (video blocked in your country, deleted…)
The script retries on 3 consecutive days, then gives up on that track.

## Code layout

```
automatic_youtube_downloader/
  __main__.py   orchestration: list, filter, download, upload
  youtube.py    playlist reading and downloading (yt-dlp)
  naming.py     "Artist - Title" from the YouTube title
  tagging.py    ID3 tags and cover
  storage.py    Google Drive, local folder, state file
scripts/get_drive_token.py   Google Drive authorization (one time only)
deploy/deploy.sh             Google Cloud deployment
```

Run the tests: `pip install pytest && pytest`
