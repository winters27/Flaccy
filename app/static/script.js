// Static asset paths - defined once at the top for maintainability
const STATIC_ASSETS = {
    FLACCY_IMAGE: '/static/flaccy.png',
    BACKGROUND_IMAGE: '/static/bg.jpg',
    FALLBACK_IMAGE: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDgiIGhlaWdodD0iNDgiIHZpZXdCb3g9IjAgMCA0OCA0OCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3Qgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQ4IiBmaWxsPSJyZ2JhKDI1NSwgMjU1LCAyNTUsIDAuMSkiIHJ4PSI0Ii8+PC9zdmc+'
};

// Helper functions for consistent asset handling
function getAlbumArtSrc(albumArtUrl) {
    return albumArtUrl || STATIC_ASSETS.FLACCY_IMAGE;
}

function createImageElement(albumArtUrl, altText = "Album Art", className = "toast-album-art") {
    const src = getAlbumArtSrc(albumArtUrl);
    const isFlaccyImage = src === STATIC_ASSETS.FLACCY_IMAGE;
    
    if (isFlaccyImage) {
        return `<img src="${src}" alt="${altText}" class="${className}" style="width: 100%; height: 100%; object-fit: cover; object-position: center;" onerror="this.src='${STATIC_ASSETS.FALLBACK_IMAGE}'">`;
    }
    
    return `<img src="${src}" alt="${altText}" class="${className}" onerror="this.src='${STATIC_ASSETS.FALLBACK_IMAGE}'">`;
}

let eventSource = null;
const activeToasts = new Map();
const toastQueue = [];
let isProcessingQueue = false;

// --- Infinite Scroll Globals ---
let currentQuery = '';
let currentSearchType = 'track';
let currentOffset = 0;
let isLoading = false;
let noMoreResults = false;
const SEARCH_LIMIT = 20;

function processToastQueue() {
    if (isProcessingQueue || toastQueue.length === 0) return;
    
    isProcessingQueue = true;
    const { downloadId, trackInfo } = toastQueue.shift();
    
    createToast(downloadId, trackInfo);
    
    setTimeout(() => {
        isProcessingQueue = false;
        processToastQueue();
    }, 150);
}

function createToast(downloadId, trackInfo) {
    if (activeToasts.has(downloadId)) {
        return;
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = 'toast';

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(trackInfo.albumArtUrl)}
            <div class="toast-progress-overlay">0%</div>
        </div>
        <div class="toast-content">
            <div class="toast-track-title" title="${trackInfo.title}">${trackInfo.title}</div>
            <div class="toast-track-details" title="${trackInfo.artist} - ${trackInfo.album}">${trackInfo.artist} - ${trackInfo.album}</div>
            <div class="toast-progress-bar-container">
                <div class="toast-progress-bar"></div>
            </div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        progress: 0,
        completed: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });
}

function updateToastProgress(downloadId, progress) {
    const toastData = activeToasts.get(downloadId);
    if (!toastData || toastData.completed) return;

    const { element } = toastData;
    const progressBar = element.querySelector('.toast-progress-bar');
    const progressOverlay = element.querySelector('.toast-progress-overlay');
    
    if (progressBar && progressOverlay) {
        progressBar.style.width = `${progress}%`;
        progressOverlay.textContent = `${Math.round(progress)}%`;
        
        toastData.progress = progress;

        if (progress >= 100 && !toastData.completed) {
            toastData.completed = true;
            toastData.completedAt = Date.now();
            progressOverlay.textContent = '✓';
            progressBar.classList.add('complete');
            
            setTimeout(() => {
                removeToast(downloadId);
            }, 2500);
        }
    }
}

function updateToastAlbumArt(downloadId, albumArtUrl) {
    const toastData = activeToasts.get(downloadId);
    if (!toastData) return;
    
    const albumArtImg = toastData.element.querySelector('.toast-album-art');
    if (albumArtImg && albumArtUrl) {
        const img = new Image();
        img.onload = function() {
            albumArtImg.src = albumArtUrl;
        };
        img.src = albumArtUrl;
    }
}

function removeToast(downloadId) {
    const toastData = activeToasts.get(downloadId);
    if (!toastData || toastData.isRemoving) return;

    toastData.isRemoving = true;
    
    const { element } = toastData;
    
    // Force the toast to animate out by removing show class
    element.classList.remove('show');
    
    
    const remove = () => {
        if (document.body.contains(element)) {
            element.remove();
        }
        activeToasts.delete(downloadId);
    };

    // Listen for transition end
    element.addEventListener('transitionend', remove, { once: true });
    
    // Shorter fallback timeout since your transition is 0.4s
    setTimeout(() => {
        remove();
    }, 500);
}

function showPlaylistLoadedToast(totalTracks) {
    const downloadId = 'playlist-download';
    if (activeToasts.has(downloadId)) {
        removeToast(downloadId);
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = 'toast';

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(null, "Album Art", "toast-album-art")}
        </div>
        <div class="toast-content">
            <div class="toast-track-title">Playlist Loaded</div>
            <div class="toast-track-details">${totalTracks} tracks ready to download.</div>
            <div class="toast-message">Click "Download Playlist" to start.</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        completed: false,
        isRemoving: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });

    // Auto-remove the "playlist loaded" toast after 10 seconds if user doesn't start download
    setTimeout(() => {
        const currentToastData = activeToasts.get(downloadId);
        // Only remove if it's still the "playlist loaded" state (title hasn't changed)
        if (currentToastData && !currentToastData.isRemoving) {
            const titleElement = currentToastData.element.querySelector('.toast-track-title');
            if (titleElement && titleElement.textContent === 'Playlist Loaded') {
                removeToast(downloadId);
            }
        }
    }, 5000);
}

function createPlaylistToast(totalTracks) {
    const downloadId = 'playlist-download';
    if (activeToasts.has(downloadId)) {
        // Update existing toast if it's already there
        const toastData = activeToasts.get(downloadId);
        const messageElement = toastData.element.querySelector('.toast-message');
        if (messageElement) {
            messageElement.textContent = `Queued ${totalTracks} tracks. Starting download...`;
        }
        return;
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = 'toast';

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(null, "Album Art", "toast-album-art")}
        </div>
        <div class="toast-content">
            <div class="toast-track-title">Playlist Download</div>
            <div class="toast-track-details">Preparing to download...</div>
            <div class="toast-message">Queued ${totalTracks} tracks. Starting download...</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        completed: false,
        isRemoving: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });
}

function removeAllToasts() {
    activeToasts.forEach((toastData, downloadId) => {
        removeToast(downloadId);
    });
}

function createErrorToast(message) {
    const toastId = `error-${Date.now()}`;
    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = 'toast error-toast';

    toast.innerHTML = `
        <div class="toast-content">
            <div class="toast-track-title">Error</div>
            <div class="toast-track-details">${message}</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(toastId, {
        element: toast,
        isRemoving: false
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });

    setTimeout(() => {
        removeToast(toastId);
    }, 5000);
}

function createSimpleToast(downloadId, trackInfo, message, type = 'info') {
    if (activeToasts.has(downloadId)) {
        return;
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = `toast ${type === 'error' ? 'error-toast' : ''}`;

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(trackInfo.albumArtUrl)}
        </div>
        <div class="toast-content">
            <div class="toast-track-title" title="${trackInfo.title}">${trackInfo.title}</div>
            <div class="toast-track-details" title="${trackInfo.artist} - ${trackInfo.album}">${trackInfo.artist} - ${trackInfo.album}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        completed: type === 'success',
        isRemoving: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });
}

// Function to update simple toast
function updateSimpleToast(downloadId, message, type = 'info') {
    const toastData = activeToasts.get(downloadId);
    if (!toastData) return;

    const { element } = toastData;
    const messageElement = element.querySelector('.toast-message');
    const statusOverlay = element.querySelector('.toast-status-overlay');
    
    if (messageElement) {
        messageElement.textContent = message;
    }
    
    if (statusOverlay) {
        statusOverlay.textContent = type === 'success' ? '✓' : type === 'error' ? '✗' : '⏳';
    }

    element.classList.remove('error-toast', 'success-toast');
    if (type === 'error') {
        element.classList.add('error-toast');
    } else if (type === 'success') {
        element.classList.add('success-toast');
    }
    
    toastData.completed = type === 'success';
}

// Clean up any stuck toasts periodically
setInterval(() => {
    activeToasts.forEach((toastData, downloadId) => {
        const now = Date.now();
        
        // Don't auto-remove playlist download toast while it's active
        if (downloadId === 'playlist-download' && !toastData.completed) {
            return; // Skip cleanup for active playlist downloads
        }
        
        // Remove completed toasts after 3 seconds
        if (toastData.completed && toastData.completedAt && now - toastData.completedAt > 3000) {
            removeToast(downloadId);
        }
        // Remove any toast that's been around for more than 30 seconds (safety net)
        else if (toastData.createdAt && now - toastData.createdAt > 30000) {
            removeToast(downloadId);
        }
    });
}, 2000);

function showTab(tabName) {
    // Remove all existing toasts
    activeToasts.forEach((toastData, downloadId) => {
        removeToast(downloadId);
    });

    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => tab.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');

    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => button.classList.remove('active'));
    document.querySelector(`.tab-button[onclick="showTab('${tabName}')"]`).classList.add('active');
}

function logMessage(message, type = 'info') {
    const log = document.getElementById('status-log');
    if (!log) {
        console.log(`[${type}] ${message}`);
        return;
    }
    const timestamp = new Date().toLocaleTimeString();
    const p = document.createElement('p');
    p.innerHTML = `<span style="color: var(--text-muted-color)">[${timestamp}]</span> ${message}`;
    
    if (type === 'error') {
        p.classList.add('error');
    } else if (type === 'success') {
        p.classList.add('success');
    }
    
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
}

function displaySearchResults(results, append = false) {
    const contentArea = document.querySelector('.content-area');
    let resultsContainer = document.getElementById('search-results');

    if (!resultsContainer) {
        resultsContainer = document.createElement('div');
        resultsContainer.id = 'search-results';
        resultsContainer.classList.add('section');
        contentArea.appendChild(resultsContainer);
    }
    
    if (!append) {
        resultsContainer.innerHTML = '';
    }

    if (!results || results.length === 0) {
        if (!append) {
            resultsContainer.innerHTML = '<p>No results found.</p>';
        }
        noMoreResults = true;
        return;
    }

    results.forEach(item => {
        const itemElement = document.createElement('div');
        itemElement.classList.add('search-result-item');

        if (currentSearchType === 'track') {
            const albumArt = getAlbumArtSrc(item.image && item.image.small ? item.image.small : null);
            const title = item.title;
            const artist = item.performer ? item.performer.name : 'Unknown Artist';

            itemElement.innerHTML = `
                <img src="${albumArt}" alt="Album Art" class="album-art" onerror="this.src='${STATIC_ASSETS.FALLBACK_IMAGE}'">
                <div class="track-info">
                    <p class="track-title">${title}</p>
                    <p class="track-artist">${artist}</p>
                </div>
                <button class="download-btn">Download</button>
            `;
            itemElement.dataset.item = JSON.stringify(item);

        } else if (currentSearchType === 'album') {
            const albumArt = getAlbumArtSrc(item.image && item.image.small ? item.image.small : null);
            const title = item.title;
            const artist = item.artist ? item.artist.name : 'Unknown Artist';

            itemElement.innerHTML = `
                <img src="${albumArt}" alt="Album Art" class="album-art" onerror="this.src='${STATIC_ASSETS.FALLBACK_IMAGE}'">
                <div class="track-info">
                    <p class="track-title">${title}</p>
                    <p class="track-artist">${artist}</p>
                </div>
                <button class="download-btn">Download Album</button>
            `;
            itemElement.dataset.item = JSON.stringify(item);
        }
        resultsContainer.appendChild(itemElement);
    });

    // --- Show More Button ---
    let existingBtn = document.getElementById('show-more-btn');
    if (existingBtn) {
        existingBtn.remove();
    }

    if (!noMoreResults) {
        let showMoreBtn = document.createElement('button');
        showMoreBtn.id = 'show-more-btn';
        showMoreBtn.textContent = 'Show More';
        showMoreBtn.classList.add('download-btn');
        showMoreBtn.addEventListener('click', () => {
            performSearch(true);
        });
        resultsContainer.appendChild(showMoreBtn);
    }
}

function setupEventSource() {
    if (eventSource) {
        eventSource.close();
    }
    
    eventSource = new EventSource("/api/status");

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);

        switch (data.type) {
            case 'info':
                if (data.track_id) {
                    const downloadId = `track-${data.track_id}`;
                    if (!activeToasts.has(downloadId)) {
                        // This is a new download starting
                        const trackInfo = { title: 'Starting Download...', artist: '', album: '' };
                        createToast(downloadId, trackInfo);
                    }
                }
                logMessage(data.message, data.type);
                break;
            case 'success':
            case 'error':
                logMessage(data.message, data.type);
                break;
            case 'download_progress':
                const { track_id, current, total } = data;
                const progress = (current / total) * 100;
                updateToastProgress(`track-${track_id}`, progress);
                break;
            case 'album_progress':
                const { album_id, current: album_current, total: album_total, album_name } = data;
                const downloadId = `album-${album_id}`;
                
                if (!activeToasts.has(downloadId)) {
                    const albumInfo = {
                        title: album_name,
                        artist: '', // Artist info isn't in the progress event, but the toast needs it
                        album: '',
                        albumArtUrl: '' // Same for album art
                    };
                    createSimpleToast(downloadId, albumInfo, `Downloading ${album_current}/${album_total}`);
                } else {
                    updateSimpleToast(downloadId, `Downloading ${album_current}/${album_total}`);
                }
                break;
            case 'heartbeat':
                // Do nothing for heartbeats
                break;
            default:
                logMessage(`Unknown event type: ${data.type}`, 'error');
        }
    };
    
    eventSource.onerror = function(err) {
        console.error("EventSource failed:", err);
        logMessage("Connection lost. Reconnecting...", "error");
        createErrorToast("Connection lost. Reconnecting...");
        eventSource.close();
        setTimeout(setupEventSource, 5000);
    };
    
    return eventSource;
}

function performSearch(append = false) {
    if (isLoading || (append && noMoreResults)) return;

    const service = document.body.dataset.service;
    if (!service) {
        logMessage('Error: No service specified on the page.', 'error');
        createErrorToast('Client error: No service specified.');
        return;
    }

    isLoading = true;
    const searchBtn = document.getElementById('search-btn');
    if (searchBtn) {
        searchBtn.classList.add('loading');
    }

    if (!append) {
        currentOffset = 0;
        noMoreResults = false;
    }
    
    logMessage(`Searching for ${currentSearchType}: "${currentQuery}" (offset: ${currentOffset})...`, 'info');

    fetch('/api/search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
            query: currentQuery, 
            type: currentSearchType,
            limit: SEARCH_LIMIT,
            offset: currentOffset,
            service: service
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            logMessage(data.error, 'error');
            createErrorToast(data.error);
            noMoreResults = true;
        } else {
            displaySearchResults(data, append);
            currentOffset += data.length;
            if (data.length < SEARCH_LIMIT) {
                noMoreResults = true;
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        logMessage('Search failed.', 'error');
        createErrorToast('Search failed. Check console for details.');
        noMoreResults = true;
    })
    .finally(() => {
        isLoading = false;
        if (searchBtn) {
            searchBtn.classList.remove('loading');
        }
    });
}

function downloadTrack(track) {
    const service = document.body.dataset.service;
    if (!service) {
        logMessage('Error: No service specified on the page.', 'error');
        createErrorToast('Client error: No service specified.');
        return;
    }

    logMessage(`Starting download: ${track.performer.name} - ${track.title}`, 'info');
    
    const downloadId = `track-${track.id}`;
    const trackInfo = {
        title: track.title,
        artist: track.performer.name,
        album: track.album.title,
        albumArtUrl: track.image.small
    };
    
    createToast(downloadId, trackInfo);
    
    fetch('/api/download-song', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track, service: service })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || 'Download failed');
            });
        }
        
        const disposition = response.headers.get('Content-Disposition');
        let filename = `${track.performer.name} - ${track.title}.flac`;
        if (disposition && disposition.indexOf('attachment') !== -1) {
            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
            const matches = filenameRegex.exec(disposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }
        
        return response.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => {
        updateToastProgress(downloadId, 100);
        
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        logMessage(`Downloaded: ${track.title}`, 'success');
        
        setTimeout(removeAllToasts, 2500);
    })
    .catch(error => {
        const toastData = activeToasts.get(downloadId);
        if (toastData) {
            toastData.element.classList.add('error-toast');
        }
        logMessage(`Download failed: ${error.message}`, 'error');
        setTimeout(() => removeToast(downloadId), 5000);
    });
}

async function downloadPlaylistInChunks(queries, service) {
    let successfulDownloads = 0;
    let failedDownloads = 0;
    let isCancelled = false;
    const totalTracks = queries.length;

    const playlistToastId = 'playlist-download';
    
    // Update the existing toast to show it's starting downloads
    const toastData = activeToasts.get(playlistToastId);
    if (toastData) {
        const titleElement = toastData.element.querySelector('.toast-track-title');
        const detailsElement = toastData.element.querySelector('.toast-track-details');
        const messageElement = toastData.element.querySelector('.toast-message');
        
        if (titleElement) titleElement.textContent = 'Playlist Downloading';
        if (detailsElement) detailsElement.textContent = `Starting download of ${totalTracks} tracks...`;
        if (messageElement) messageElement.textContent = 'Preparing downloads...';
    } else {
        // Fallback in case the toast wasn't created
        createPlaylistToast(totalTracks);
    }

    const cancelBtn = document.getElementById('cancel-playlist-btn');
    const startBtn = document.getElementById('start-playlist-btn');

    const cancelHandler = () => {
        isCancelled = true;
        logMessage('Playlist download cancelled by user.', 'info');
        
        const startBtn = document.getElementById('start-playlist-btn');
        const cancelBtn = document.getElementById('cancel-playlist-btn');
        
        if (startBtn) startBtn.style.display = 'inline-block';
        if (cancelBtn) cancelBtn.style.display = 'none';
    };

    if (cancelBtn) {
        const newCancelBtn = cancelBtn.cloneNode(true);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);
        newCancelBtn.addEventListener('click', cancelHandler, { once: true });
    }

    for (let i = 0; i < totalTracks; i++) {
        if (isCancelled) break;

        const query = queries[i];
        const progressMessage = `Downloading ${i + 1}/${totalTracks}`;
        
        // Update the message element directly instead of using updateSimpleToast
        const currentToastData = activeToasts.get(playlistToastId);
        if (currentToastData) {
            const messageElement = currentToastData.element.querySelector('.toast-message');
            if (messageElement) {
                messageElement.textContent = progressMessage;
            }
        }
        
        logMessage(`${progressMessage}: ${query}`, 'info');

        try {
            const response = await fetch('/api/download-playlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    queries: [query], // Send one query at a time
                    service: service
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Server error: ${response.status}`);
            }

            const data = await response.json();
            if (data.results && data.results[0].status === 'success') {
                successfulDownloads++;
            } else {
                failedDownloads++;
                logMessage(`Failed to download: ${query}. Reason: ${data.results[0].message || 'Unknown'}`, 'error');
            }

        } catch (err) {
            console.error(`[error] Failed to download ${query}:`, err);
            logMessage(`Error downloading ${query}: ${err.message}`, 'error');
            failedDownloads++;
        }
    }

    if (!isCancelled) {
        const finalMessage = `Finished. Success: ${successfulDownloads}, Failed: ${failedDownloads}`;
        
        // Update the final message
        const finalToastData = activeToasts.get(playlistToastId);
        if (finalToastData) {
            const messageElement = finalToastData.element.querySelector('.toast-message');
            const titleElement = finalToastData.element.querySelector('.toast-track-title');
            
            if (messageElement) messageElement.textContent = finalMessage;
            if (titleElement) titleElement.textContent = 'Playlist Complete';
            
            // Mark as completed for cleanup
            finalToastData.completed = true;
            finalToastData.completedAt = Date.now();
        }
        
        logMessage(`Playlist download finished. Success: ${successfulDownloads}, Failed: ${failedDownloads}`, 'info');
        if (startBtn) startBtn.style.display = 'inline-block';
        if (cancelBtn) cancelBtn.style.display = 'none';
        
        // Remove the toast after showing completion for 5 seconds
        setTimeout(() => removeToast(playlistToastId), 5000);
    } else {
        removeToast(playlistToastId);
    }
}

async function downloadAlbum(album) {
    const service = document.body.dataset.service;
    if (!service) {
        logMessage('Error: No service specified on the page.', 'error');
        createErrorToast('Client error: No service specified.');
        return;
    }

    logMessage(`Starting album download: ${album.artist.name} - ${album.title}`, 'info');
    
    const downloadId = `album-${album.id}`;
    const albumInfo = {
        title: album.title,
        artist: album.artist.name,
        album: album.title,
        albumArtUrl: album.image.small
    };
    
    createSimpleToast(downloadId, albumInfo, 'Downloading album...');

    try {
        const response = await fetch('/api/download-album', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ album_id: album.id, service: service })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Album download failed');
        }

        const disposition = response.headers.get('Content-Disposition');
        let filename = 'album.zip';
        if (disposition && disposition.indexOf('attachment') !== -1) {
            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
            const matches = filenameRegex.exec(disposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        updateSimpleToast(downloadId, 'Album Download Complete!', 'success');
        logMessage(`Album downloaded: ${filename}`, 'success');
        setTimeout(removeAllToasts, 2500);
        
    } catch (error) {
        const downloadId = `album-${album.id}`;
        updateSimpleToast(downloadId, 'Album Download Failed', 'error');
        logMessage(`Album download failed: ${error.message}`, 'error');
        setTimeout(removeAllToasts, 3000);
    }
}

function cancelDownloads() {
    fetch('/api/cancel-downloads', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            logMessage('All downloads have been cancelled.', 'info');
        } else {
            logMessage('Failed to cancel downloads.', 'error');
        }
        
        // Move button visibility changes inside the promise
        const cancelBtn = document.getElementById('cancel-playlist-btn');
        const startBtn = document.getElementById('start-playlist-btn');
        
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (startBtn) startBtn.style.display = 'inline-block';
    })
    .catch(error => {
        console.error('Error:', error);
        logMessage('Failed to send cancel request.', 'error');
        
        // Also handle button visibility on error
        const cancelBtn = document.getElementById('cancel-playlist-btn');
        const startBtn = document.getElementById('start-playlist-btn');
        
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (startBtn) startBtn.style.display = 'inline-block';
    });

}

function initializeSearch() {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');

    if (searchBtn) {
        // Add the loader and text span to the button
        searchBtn.innerHTML = '<span class="btn-text">Search</span><div class="loader"></div>';
        searchBtn.addEventListener('click', () => {
            const query = searchInput.value;
            if (!query) {
                logMessage('Please enter a search query.', 'error');
                return;
            }
            
            currentQuery = query;
            const checkedRadio = document.querySelector('input[name="search-type"]:checked');
            currentSearchType = checkedRadio ? checkedRadio.value : 'track';
            
            performSearch(false);
        });
    }

    // Add Enter key support for search
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                if (searchBtn) {
                    searchBtn.click();
                }
            }
        });
    }
}

function selectService(service) {
    document.body.dataset.service = service;
    document.querySelectorAll('.service-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.service === service);
    });
    // Clear search results when switching services
    const resultsContainer = document.getElementById('search-results');
    if (resultsContainer) {
        resultsContainer.innerHTML = '';
    }
    currentQuery = '';
    currentOffset = 0;
    noMoreResults = false;
}

document.addEventListener('DOMContentLoaded', () => {
    let toastContainer = document.getElementById('toast-queue-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-queue-container';
        document.body.appendChild(toastContainer);
    }
    setupEventSource();

    const servicePicker = document.querySelector('.service-picker');
    if (servicePicker) {
        servicePicker.addEventListener('click', (e) => {
            const serviceOption = e.target.closest('.service-option');
            if (serviceOption) {
                selectService(serviceOption.dataset.service);
            }
        });
    }

    // Set initial service
    selectService('tidal');

    const contentArea = document.querySelector('.content-area');
    contentArea.addEventListener('click', function(e) {
        if (e.target.classList.contains('download-btn')) {
            const item = e.target.closest('.search-result-item');
            if (!item) return;
            
            const itemData = JSON.parse(item.dataset.item);
            
            const searchType = item.closest('#search-results') ? currentSearchType : 'track';

            if (searchType === 'track') {
                downloadTrack(itemData);
            } else if (searchType === 'album') {
                downloadAlbum(itemData);
            }
        }
    });

    const playlistInput = document.getElementById('playlist-input');
    const startPlaylistBtn = document.getElementById('start-playlist-btn');
    const cancelBtn = document.getElementById('cancel-playlist-btn');

    if (playlistInput) {
        playlistInput.addEventListener('change', () => {
            const file = playlistInput.files[0];
            if (!file) {
                return;
            }
            const reader = new FileReader();
            reader.onload = (e) => {
                const content = e.target.result;
                const lines = content.split('\n').filter(line => line.includes(' - '));
                showPlaylistLoadedToast(lines.length);
            };
            reader.readAsText(file);
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelDownloads);
    }

    if (startPlaylistBtn) {
        startPlaylistBtn.addEventListener('click', () => {
            const file = playlistInput.files[0];
            if (!file) {
                logMessage('Please select a playlist file.', 'error');
                return;
            }
            
            const reader = new FileReader();
            reader.onload = function(e) {
                const content = e.target.result;
                const lines = content.split('\n').filter(line => line.includes(' - '));
                logMessage(`Queueing ${lines.length} tracks from playlist...`, 'info');

                startPlaylistBtn.style.display = 'none';
                const cancelBtn = document.getElementById('cancel-playlist-btn');
                if (cancelBtn) {
                    cancelBtn.style.display = 'inline-block';
                }

                const service = document.body.dataset.service;
                if (!service) {
                    logMessage('Error: No service specified on the page.', 'error');
                    createErrorToast('Client error: No service specified.');
                    if (startPlaylistBtn) startPlaylistBtn.style.display = 'inline-block';
                    if (cancelBtn) cancelBtn.style.display = 'none';
                    return;
                }

                downloadPlaylistInChunks(lines, service);
            };
            reader.readAsText(file);
        });
    }

    // If the search input exists on the current page, initialize it.
    if (document.getElementById('search-input')) {
        initializeSearch();
    }
});

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});
