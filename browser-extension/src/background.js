/**
 * ActivityWatch Enhanced - Browser Extension Background Script
 *
 * Captures browser activity and sends to ActivityWatch server.
 * Works with both the standard aw-server and aw-watcher-enhanced.
 */

// Configuration
const CONFIG = {
  serverUrl: 'http://localhost:5600',
  pollInterval: 5000, // 5 seconds
  pulsetime: 6.0,
  bucketId: null, // Set on init
  enabled: true,
  trackUrls: true,
  trackTitles: true,
  excludePatterns: [],
  excludeDomains: ['localhost', '127.0.0.1'],
  incognitoTracking: false,
};

// State
let currentTab = null;
let lastHeartbeat = null;
let isConnected = false;

/**
 * Initialize the extension
 */
async function init() {
  console.log('ActivityWatch Enhanced: Initializing...');

  // Load saved settings
  await loadSettings();

  // Get hostname for bucket ID
  const hostname = await getHostname();
  CONFIG.bucketId = `aw-watcher-web-enhanced_${hostname}`;

  // Create bucket
  await createBucket();

  // Start heartbeat loop
  startHeartbeatLoop();

  // Listen for tab changes
  chrome.tabs.onActivated.addListener(handleTabActivated);
  chrome.tabs.onUpdated.addListener(handleTabUpdated);
  chrome.windows.onFocusChanged.addListener(handleWindowFocusChanged);

  console.log('ActivityWatch Enhanced: Initialized');
}

/**
 * Load settings from storage
 */
async function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get({
      serverUrl: CONFIG.serverUrl,
      enabled: CONFIG.enabled,
      trackUrls: CONFIG.trackUrls,
      trackTitles: CONFIG.trackTitles,
      excludePatterns: CONFIG.excludePatterns,
      excludeDomains: CONFIG.excludeDomains,
      incognitoTracking: CONFIG.incognitoTracking,
    }, (items) => {
      Object.assign(CONFIG, items);
      resolve();
    });
  });
}

/**
 * Save settings to storage
 */
async function saveSettings(settings) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(settings, resolve);
  });
}

/**
 * Get hostname (for bucket naming)
 */
async function getHostname() {
  try {
    const response = await fetch(`${CONFIG.serverUrl}/api/0/info`);
    const data = await response.json();
    return data.hostname || 'unknown';
  } catch (error) {
    console.error('Failed to get hostname:', error);
    return 'unknown';
  }
}

/**
 * Create bucket on ActivityWatch server
 */
async function createBucket() {
  try {
    const response = await fetch(`${CONFIG.serverUrl}/api/0/buckets/${CONFIG.bucketId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client: 'aw-watcher-web-enhanced',
        type: 'web.tab.current',
        hostname: CONFIG.bucketId.split('_')[1],
      }),
    });

    if (response.ok || response.status === 304) {
      isConnected = true;
      console.log('Bucket created/verified:', CONFIG.bucketId);
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    isConnected = false;
    console.error('Failed to create bucket:', error);
  }
}

/**
 * Send heartbeat to ActivityWatch server
 */
async function sendHeartbeat(data) {
  if (!CONFIG.enabled || !isConnected) return;

  const event = {
    timestamp: new Date().toISOString(),
    duration: 0,
    data: data,
  };

  try {
    const response = await fetch(
      `${CONFIG.serverUrl}/api/0/buckets/${CONFIG.bucketId}/heartbeat?pulsetime=${CONFIG.pulsetime}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(event),
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    lastHeartbeat = Date.now();
    isConnected = true;
  } catch (error) {
    console.error('Failed to send heartbeat:', error);
    isConnected = false;
    // Try to reconnect
    setTimeout(createBucket, 10000);
  }
}

/**
 * Get current tab data
 */
async function getCurrentTabData() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length === 0) {
        resolve(null);
        return;
      }

      const tab = tabs[0];

      // Skip if incognito and not tracking
      if (tab.incognito && !CONFIG.incognitoTracking) {
        resolve(null);
        return;
      }

      // Skip browser internal pages
      if (!tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://') ||
          tab.url.startsWith('about:') || tab.url.startsWith('moz-extension://')) {
        resolve(null);
        return;
      }

      resolve(tab);
    });
  });
}

/**
 * Process tab and create event data
 */
function processTabData(tab) {
  if (!tab || !tab.url) return null;

  try {
    const url = new URL(tab.url);

    // Check domain exclusions
    if (CONFIG.excludeDomains.some(d => url.hostname.includes(d))) {
      return null;
    }

    // Check pattern exclusions
    if (CONFIG.excludePatterns.some(p => {
      try {
        return new RegExp(p, 'i').test(tab.url);
      } catch {
        return false;
      }
    })) {
      return null;
    }

    const data = {
      url: CONFIG.trackUrls ? tab.url : '[redacted]',
      title: CONFIG.trackTitles ? (tab.title || '') : '[redacted]',
      domain: url.hostname,
      incognito: tab.incognito,
      tabCount: 0, // Will be updated
      audible: tab.audible || false,
    };

    // Add additional metadata
    data.protocol = url.protocol.replace(':', '');
    data.path = url.pathname;

    // Categorize based on domain
    data.category = categorizeDomain(url.hostname, url.pathname);

    return data;
  } catch (error) {
    console.error('Error processing tab:', error);
    return null;
  }
}

/**
 * Categorize based on domain
 */
function categorizeDomain(hostname, path) {
  const domain = hostname.toLowerCase();

  // Development
  if (domain.includes('github.com')) {
    if (path.includes('/pull/')) return 'Work/Development/Code Review';
    if (path.includes('/issues/')) return 'Work/Development/Issues';
    return 'Work/Development';
  }
  if (domain.includes('gitlab.com') || domain.includes('bitbucket.org')) {
    return 'Work/Development';
  }
  if (domain.includes('stackoverflow.com') || domain.includes('stackexchange.com')) {
    return 'Work/Development/Research';
  }

  // Documentation
  if (domain.includes('docs.') || domain.includes('documentation.') ||
      domain.includes('developer.') || domain.includes('devdocs.io')) {
    return 'Work/Development/Documentation';
  }

  // Communication
  if (domain.includes('mail.google.com') || domain.includes('outlook.') ||
      domain.includes('mail.yahoo.com')) {
    return 'Work/Communication/Email';
  }
  if (domain.includes('slack.com') || domain.includes('discord.com') ||
      domain.includes('teams.microsoft.com')) {
    return 'Work/Communication/Chat';
  }
  if (domain.includes('meet.google.com') || domain.includes('zoom.us') ||
      domain.includes('webex.com')) {
    return 'Work/Communication/Meetings';
  }

  // Project Management
  if (domain.includes('jira') || domain.includes('asana.com') ||
      domain.includes('trello.com') || domain.includes('monday.com') ||
      domain.includes('linear.app') || domain.includes('notion.so')) {
    return 'Work/Project Management';
  }

  // Google Workspace
  if (domain.includes('docs.google.com')) {
    if (path.includes('/document/')) return 'Work/Documentation/Writing';
    if (path.includes('/spreadsheets/')) return 'Work/Data/Spreadsheets';
    if (path.includes('/presentation/')) return 'Work/Presentation';
    return 'Work/Documentation';
  }
  if (domain.includes('drive.google.com')) {
    return 'Work/Files';
  }

  // Design
  if (domain.includes('figma.com') || domain.includes('canva.com') ||
      domain.includes('sketch.com')) {
    return 'Work/Design';
  }

  // Social Media
  if (domain.includes('twitter.com') || domain.includes('x.com') ||
      domain.includes('facebook.com') || domain.includes('instagram.com') ||
      domain.includes('linkedin.com') || domain.includes('reddit.com')) {
    return 'Personal/Social Media';
  }

  // Entertainment
  if (domain.includes('youtube.com') || domain.includes('netflix.com') ||
      domain.includes('twitch.tv') || domain.includes('spotify.com') ||
      domain.includes('hulu.com') || domain.includes('disneyplus.com')) {
    return 'Personal/Entertainment';
  }

  // Shopping
  if (domain.includes('amazon.') || domain.includes('ebay.') ||
      domain.includes('etsy.com') || domain.includes('shopify.com')) {
    return 'Personal/Shopping';
  }

  // News
  if (domain.includes('news.') || domain.includes('cnn.com') ||
      domain.includes('bbc.') || domain.includes('nytimes.com') ||
      domain.includes('theguardian.com')) {
    return 'Personal/News';
  }

  // Learning
  if (domain.includes('udemy.com') || domain.includes('coursera.org') ||
      domain.includes('edx.org') || domain.includes('linkedin.com/learning') ||
      domain.includes('pluralsight.com')) {
    return 'Research/Learning';
  }

  return null; // Unknown
}

/**
 * Main heartbeat function
 */
async function heartbeat() {
  const tab = await getCurrentTabData();
  if (!tab) return;

  const data = processTabData(tab);
  if (!data) return;

  // Get tab count
  chrome.tabs.query({}, (tabs) => {
    data.tabCount = tabs.length;
    sendHeartbeat(data);
  });

  currentTab = tab;
}

/**
 * Start the heartbeat loop
 */
function startHeartbeatLoop() {
  // Initial heartbeat
  heartbeat();

  // Set up alarm for periodic heartbeats
  chrome.alarms.create('heartbeat', { periodInMinutes: CONFIG.pollInterval / 60000 });

  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'heartbeat') {
      heartbeat();
    }
  });
}

/**
 * Handle tab activation
 */
function handleTabActivated(activeInfo) {
  heartbeat();
}

/**
 * Handle tab updates (URL/title changes)
 */
function handleTabUpdated(tabId, changeInfo, tab) {
  if (changeInfo.url || changeInfo.title) {
    if (tab.active) {
      heartbeat();
    }
  }
}

/**
 * Handle window focus changes
 */
function handleWindowFocusChanged(windowId) {
  if (windowId !== chrome.windows.WINDOW_ID_NONE) {
    heartbeat();
  }
}

/**
 * Message handler for popup/options communication
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'getStatus':
      sendResponse({
        enabled: CONFIG.enabled,
        connected: isConnected,
        lastHeartbeat: lastHeartbeat,
        currentUrl: currentTab?.url,
        bucketId: CONFIG.bucketId,
      });
      break;

    case 'setEnabled':
      CONFIG.enabled = message.enabled;
      saveSettings({ enabled: message.enabled });
      if (message.enabled) {
        heartbeat();
      }
      sendResponse({ success: true });
      break;

    case 'getSettings':
      sendResponse(CONFIG);
      break;

    case 'saveSettings':
      Object.assign(CONFIG, message.settings);
      saveSettings(message.settings);
      sendResponse({ success: true });
      break;

    case 'testConnection':
      createBucket().then(() => {
        sendResponse({ connected: isConnected });
      });
      return true; // Async response

    default:
      sendResponse({ error: 'Unknown message type' });
  }
});

// Initialize on load
init();
