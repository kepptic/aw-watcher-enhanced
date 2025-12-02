# ActivityWatch Enhanced - Browser Extension

Browser extension for enhanced ActivityWatch tracking with URL capture, automatic categorization, and client/project detection.

## Features

- **Full URL Tracking**: Captures complete URLs, not just page titles
- **Automatic Categorization**: Classifies browsing activity (Development, Email, Social Media, etc.)
- **Client/Project Detection**: Detects clients from keywords in URLs and page titles
- **Privacy Controls**: Exclude specific domains and URL patterns
- **Incognito Support**: Optional tracking for private browsing
- **Real-time Status**: See connection status and tracking activity

## Installation

### Chrome / Chromium / Edge / Brave

1. Open `chrome://extensions/` (or equivalent)
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select the `browser-extension` folder

### Firefox

1. Open `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `manifest.firefox.json` from the `browser-extension` folder

**Note**: For permanent Firefox installation, the extension needs to be signed by Mozilla.

## Usage

### Popup

Click the extension icon to see:
- Connection status to ActivityWatch server
- Current page being tracked
- Auto-detected category
- Quick enable/disable toggle

### Settings

Access settings by clicking "Settings" in the popup or right-clicking the icon:

- **Server URL**: ActivityWatch server address (default: `http://localhost:5600`)
- **Track URLs**: Enable/disable full URL tracking
- **Track Titles**: Enable/disable page title tracking
- **Incognito Tracking**: Track private browsing (disabled by default)
- **Excluded Domains**: Domains to never track (one per line)
- **Excluded Patterns**: Regex patterns for URLs to exclude
- **Client Keywords**: Define client detection keywords

### Client Keywords Format

```
acme-corp: acme, project-x, acme.com
bigcorp: bigcorp, initiative-y
internal: company-name, intranet
```

## Data Schema

Events are sent to bucket `aw-watcher-web-enhanced_{hostname}`:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "duration": 5.0,
  "data": {
    "url": "https://github.com/user/repo/pull/123",
    "title": "Fix bug #456 - Pull Request",
    "domain": "github.com",
    "path": "/user/repo/pull/123",
    "protocol": "https",
    "category": "Work/Development/Code Review",
    "tabCount": 15,
    "audible": false,
    "incognito": false
  }
}
```

## Category Hierarchy

The extension automatically categorizes pages:

```
Work/
├── Development/
│   ├── Code Review (github.com/*/pull/*)
│   ├── Issues (github.com/*/issues/*)
│   ├── Research (stackoverflow.com)
│   └── Documentation (docs.*, devdocs.io)
├── Communication/
│   ├── Email (mail.google.com, outlook.*)
│   ├── Chat (slack.com, discord.com)
│   └── Meetings (meet.google.com, zoom.us)
├── Documentation (docs.google.com/document)
├── Data/Spreadsheets (docs.google.com/spreadsheets)
├── Design (figma.com, canva.com)
├── Project Management (jira, trello, asana)
└── Files (drive.google.com)

Personal/
├── Social Media (twitter, facebook, reddit)
├── Entertainment (youtube, netflix, spotify)
├── Shopping (amazon, ebay)
└── News (cnn, bbc, nytimes)

Research/
└── Learning (udemy, coursera, pluralsight)
```

## Privacy

- All data is stored locally on your ActivityWatch server
- No data is sent to external services
- Incognito tabs are not tracked by default
- Configure exclusions for sensitive domains

## Permissions Explained

- `tabs`: Required to access tab URLs and titles
- `activeTab`: Required to get current tab information
- `storage`: Required to save settings
- `alarms`: Required for periodic heartbeat
- `localhost:5600`: Required to communicate with ActivityWatch server

## Troubleshooting

### Extension shows "Disconnected"

1. Ensure ActivityWatch is running (`aw-server` or `aw-qt`)
2. Check server URL in settings (default: `http://localhost:5600`)
3. Click "Test Connection" in settings

### Some pages not tracked

1. Check if domain is in excluded list
2. Check if URL matches an exclude pattern
3. Browser internal pages (chrome://, about:) are never tracked

### Icons not showing

Generate PNG icons from the SVG:
```bash
# Using ImageMagick
convert -background none icons/icon.svg -resize 16x16 icons/icon16.png
convert -background none icons/icon.svg -resize 32x32 icons/icon32.png
convert -background none icons/icon.svg -resize 48x48 icons/icon48.png
convert -background none icons/icon.svg -resize 128x128 icons/icon128.png
```

Or use an online SVG to PNG converter.

## Development

### Building

No build step required - the extension runs directly from source.

### Testing

1. Load the extension in developer mode
2. Open the browser console (F12) > Extensions > ActivityWatch Enhanced
3. Check for errors in the background script

### Contributing

1. Fork the repository
2. Make changes
3. Test with both Chrome and Firefox
4. Submit a pull request
