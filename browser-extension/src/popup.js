/**
 * Popup script for ActivityWatch Enhanced browser extension
 */

document.addEventListener('DOMContentLoaded', () => {
  const connectionDot = document.getElementById('connectionDot');
  const connectionStatus = document.getElementById('connectionStatus');
  const eventsToday = document.getElementById('eventsToday');
  const enabledToggle = document.getElementById('enabledToggle');
  const pageTitle = document.getElementById('pageTitle');
  const pageUrl = document.getElementById('pageUrl');
  const pageCategory = document.getElementById('pageCategory');
  const lastSync = document.getElementById('lastSync');

  // Get status from background script
  function updateStatus() {
    chrome.runtime.sendMessage({ type: 'getStatus' }, (response) => {
      if (chrome.runtime.lastError) {
        console.error('Error getting status:', chrome.runtime.lastError);
        setDisconnected();
        return;
      }

      // Update connection status
      if (response.connected) {
        connectionDot.className = 'status-dot connected';
        connectionStatus.textContent = 'Connected';
      } else {
        connectionDot.className = 'status-dot disconnected';
        connectionStatus.textContent = 'Disconnected';
      }

      // Update enabled toggle
      enabledToggle.checked = response.enabled;

      if (!response.enabled) {
        connectionDot.className = 'status-dot disabled';
        connectionStatus.textContent = 'Disabled';
      }

      // Update last sync time
      if (response.lastHeartbeat) {
        const seconds = Math.floor((Date.now() - response.lastHeartbeat) / 1000);
        if (seconds < 60) {
          lastSync.textContent = `${seconds}s ago`;
        } else {
          lastSync.textContent = `${Math.floor(seconds / 60)}m ago`;
        }
      } else {
        lastSync.textContent = 'Never';
      }
    });
  }

  function setDisconnected() {
    connectionDot.className = 'status-dot disconnected';
    connectionStatus.textContent = 'Error';
  }

  // Get current tab info
  function updateCurrentTab() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length === 0) {
        pageTitle.textContent = 'No active tab';
        pageUrl.textContent = '-';
        pageCategory.textContent = 'Unknown';
        return;
      }

      const tab = tabs[0];

      // Check if it's a browser internal page
      if (!tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('about:')) {
        pageTitle.textContent = 'Browser Page';
        pageUrl.textContent = '(not tracked)';
        pageCategory.textContent = 'System';
        return;
      }

      pageTitle.textContent = tab.title || 'Untitled';

      try {
        const url = new URL(tab.url);
        pageUrl.textContent = url.hostname + url.pathname.substring(0, 30) + (url.pathname.length > 30 ? '...' : '');

        // Get category from background
        const category = categorizeUrl(url.hostname, url.pathname);
        pageCategory.textContent = category || 'Uncategorized';
      } catch {
        pageUrl.textContent = tab.url.substring(0, 40) + '...';
        pageCategory.textContent = 'Unknown';
      }
    });
  }

  // Simple categorization (mirrors background.js)
  function categorizeUrl(hostname, path) {
    const domain = hostname.toLowerCase();

    if (domain.includes('github.com')) {
      if (path.includes('/pull/')) return 'Code Review';
      return 'Development';
    }
    if (domain.includes('stackoverflow.com')) return 'Research';
    if (domain.includes('mail.google.com') || domain.includes('outlook.')) return 'Email';
    if (domain.includes('slack.com') || domain.includes('discord.com')) return 'Chat';
    if (domain.includes('docs.google.com')) return 'Documents';
    if (domain.includes('youtube.com') || domain.includes('netflix.com')) return 'Entertainment';
    if (domain.includes('twitter.com') || domain.includes('facebook.com')) return 'Social Media';
    if (domain.includes('amazon.')) return 'Shopping';

    return null;
  }

  // Handle toggle change
  enabledToggle.addEventListener('change', () => {
    chrome.runtime.sendMessage({
      type: 'setEnabled',
      enabled: enabledToggle.checked
    }, () => {
      updateStatus();
    });
  });

  // Fetch events count (if possible)
  async function fetchEventsCount() {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'getSettings' });
      const serverUrl = response.serverUrl || 'http://localhost:5600';
      const bucketId = response.bucketId;

      if (!bucketId) {
        eventsToday.textContent = '-';
        return;
      }

      // Get today's date range
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const start = today.toISOString();

      const countResponse = await fetch(
        `${serverUrl}/api/0/buckets/${bucketId}/events/count?start=${start}`
      );

      if (countResponse.ok) {
        const count = await countResponse.json();
        eventsToday.textContent = count.toString();
      } else {
        eventsToday.textContent = '-';
      }
    } catch (error) {
      console.error('Failed to fetch events count:', error);
      eventsToday.textContent = '-';
    }
  }

  // Initial updates
  updateStatus();
  updateCurrentTab();
  fetchEventsCount();

  // Refresh periodically while popup is open
  setInterval(updateStatus, 5000);
});
