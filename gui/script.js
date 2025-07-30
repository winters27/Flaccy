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

    const albumArt = trackInfo.albumArtUrl || 'flaccy.png';

    toast.innerHTML = `
        <div class="toast-album-art-container">
            <img src="${albumArt}" alt="Album Art" class="toast-album-art" onerror="this.src='flaccy.png'">
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
        completed: false
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
    element.classList.remove('show');
    
    const remove = () => {
        if (document.body.contains(element)) {
            element.remove();
        }
        activeToasts.delete(downloadId);
    };

    element.addEventListener('transitionend', remove, { once: true });
    
    // Fallback timeout in case transitionend doesn't fire
    setTimeout(remove, 1000);
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

// Clean up any stuck toasts periodically
setInterval(() => {
    activeToasts.forEach((toastData, downloadId) => {
        if (toastData.completed && toastData.completedAt && Date.now() - toastData.completedAt > 5000) {
            removeToast(downloadId);
        }
    });
}, 5000);

function showTab(tabName) {
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
            const albumArt = item.album && item.album.image && item.album.image.small ? item.album.image.small : 'flaccy.png';
            const title = item.title;
            const artist = item.performer ? item.performer.name : 'Unknown Artist';

            itemElement.innerHTML = `
                <img src="${albumArt}" alt="Album Art" class="album-art">
                <div class="track-info">
                    <p class="track-title">${title}</p>
                    <p class="track-artist">${artist}</p>
                </div>
                <button class="download-btn">Download</button>
            `;
            // For TRACK items:
            itemElement.dataset.item = JSON.stringify({
                id: item.id,
                title: item.title,
                artist: item.performer.name,
                album: item.album.title,
                album_id: item.album.id,
                album_art: item.album.image.small
            });

        } else if (currentSearchType === 'album') {
            const albumArt = item.image && item.image.small ? item.image.small : 'flaccy.png';
            const title = item.title;
            const artist = item.artist ? item.artist.name : 'Unknown Artist';

            itemElement.innerHTML = `
                <img src="${albumArt}" alt="Album Art" class="album-art">
                <div class="track-info">
                    <p class="track-title">${title}</p>
                    <p class="track-artist">${artist}</p>
                </div>
                <button class="download-btn">Download Album</button>
            `;
            // For ALBUM items:
            itemElement.dataset.item = JSON.stringify({
                id: item.id,
                title: item.title,
                artist: item.artist.name,
                album_art: item.image.small
            });
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
            case 'download_start':
                toastQueue.push({
                    downloadId: data.download_id,
                    trackInfo: data.track_info
                });
                processToastQueue();
                break;
            case 'update_toast_art':
                updateToastAlbumArt(data.download_id, data.albumArtUrl);
                break;
            case 'progress':
                updateToastProgress(data.download_id, data.progress);
                break;
            case 'info':
            case 'success':
            case 'error':
                logMessage(data.message, data.type);
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

    isLoading = true;
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
            offset: currentOffset
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
    });
}

function downloadTrack(track) {
    fetch('/api/download-song', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track })
    })
    .then(response => {
        if (response.status === 401) {
            return response.json().then(data => {
                throw new Error(data.error || 'Authentication required');
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            logMessage(data.error, 'error');
            createErrorToast(data.error);
            if (data.error.includes('Qobuz session expired')) {
                showQobuzLoginModal();
            }
        } else {
            logMessage(`Queued for download: ${track.title}`, 'info');
        }
    })
    .catch(error => {
        logMessage(`Download failed: ${error.message}`, 'error');
        createErrorToast(`Download failed: ${error.message}`);
    });
}

function downloadAlbum(albumId) {
    fetch('/api/download-album', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ album_id: albumId })
    })
    .then(response => {
        if (response.status === 401) {
            return response.json().then(data => {
                throw new Error(data.error || 'Authentication required');
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            logMessage(data.error, 'error');
            createErrorToast(data.error);
            if (data.error.includes('Qobuz session expired')) {
                showQobuzLoginModal();
            }
        } else {
            logMessage(data.message, 'success');
        }
    })
    .catch(error => {
        logMessage(`Album download failed: ${error.message}`, 'error');
        createErrorToast(`Album download failed: ${error.message}`);
    });
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
    })
    .catch(error => {
        console.error('Error:', error);
        logMessage('Failed to send cancel request.', 'error');
    });

    document.getElementById('cancel-playlist-btn').style.display = 'none';
    document.getElementById('start-playlist-btn').style.display = 'inline-block';
}

function showQobuzLoginModal() {
    // Check if modal already exists
    if (document.getElementById('qobuz-login-modal')) {
        return;
    }

    const modalHTML = `
        <div id="qobuz-login-modal" class="modal-overlay">
            <div class="modal-content">
                <h2>Qobuz Login Required</h2>
                <p>Your session has expired. Please log in to Qobuz to continue.</p>
                <form id="qobuz-login-form">
                    <input type="email" id="qobuz-email" placeholder="Qobuz Email" required>
                    <input type="password" id="qobuz-password" placeholder="Qobuz Password" required>
                    <button type="submit">Login to Qobuz</button>
                </form>
                <p id="qobuz-login-error" class="error" style="display:none;"></p>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);

    const form = document.getElementById('qobuz-login-form');
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const email = document.getElementById('qobuz-email').value;
        const password = document.getElementById('qobuz-password').value;
        const errorEl = document.getElementById('qobuz-login-error');

        fetch('/api/qobuz-login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                logMessage('Qobuz login successful!', 'success');
                document.getElementById('qobuz-login-modal').remove();
            } else {
                errorEl.textContent = data.error || 'An unknown error occurred.';
                errorEl.style.display = 'block';
            }
        })
        .catch(err => {
            errorEl.textContent = `Request failed: ${err}`;
            errorEl.style.display = 'block';
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const qobuzLoginBtn = document.getElementById('qobuz-login-btn');

    function updateQobuzLoginButton(isLoggedIn) {
        if (isLoggedIn) {
            qobuzLoginBtn.textContent = 'Logged in to Qobuz';
            qobuzLoginBtn.disabled = true;
        } else {
            qobuzLoginBtn.textContent = 'Login to Qobuz';
            qobuzLoginBtn.disabled = false;
        }
    }

    fetch('/api/check-session')
        .then(response => response.json())
        .then(data => {
            updateQobuzLoginButton(data.qobuz_logged_in);
        });
        
    setupEventSource();

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
                downloadAlbum(itemData.id);
            }
        }
    });

    const playlistInput = document.getElementById('playlist-input');
    const startPlaylistBtn = document.getElementById('start-playlist-btn');
    const cancelBtn = document.getElementById('cancel-playlist-btn');

    cancelBtn.addEventListener('click', cancelDownloads);

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
            document.getElementById('cancel-playlist-btn').style.display = 'inline-block';

            const formData = new FormData();
            formData.append('playlist', file);

            fetch('/api/download-playlist', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    logMessage(data.error, 'error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                logMessage('Failed to start playlist download.', 'error');
            })
            .finally(() => {
                startPlaylistBtn.style.display = 'inline-block';
                document.getElementById('cancel-playlist-btn').style.display = 'none';
            });
        };
        reader.readAsText(file);
    });

    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');

    searchBtn.addEventListener('click', () => {
        const query = searchInput.value;
        if (!query) {
            logMessage('Please enter a search query.', 'error');
            return;
        }
        
        currentQuery = query;
        currentSearchType = document.querySelector('input[name="search-type"]:checked').value;
        
        performSearch(false);
    });

    // Add Enter key support for search
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            searchBtn.click();
        }
    });

    qobuzLoginBtn.addEventListener('click', () => {
        showQobuzLoginModal();
    });
});

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});
