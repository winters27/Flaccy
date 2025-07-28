let totalDownloads = 0;
let completedDownloads = 0;
let eventSource = null;

// --- Infinite Scroll Globals ---
let currentQuery = '';
let currentSearchType = 'track';
let currentOffset = 0;
let isLoading = false;
let noMoreResults = false;
const SEARCH_LIMIT = 20;


function resetProgressBar() {
    totalDownloads = 0;
    completedDownloads = 0;
    const progressBar = document.getElementById('progress-bar');
    progressBar.style.width = '0%';
}

function updateProgressBar() {
    if (totalDownloads > 0) {
        const percent = (completedDownloads / totalDownloads) * 100;
        const progressBar = document.getElementById('progress-bar');
        progressBar.style.width = `${percent}%`;
    }
}

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
        contentArea.insertBefore(resultsContainer, contentArea.firstChild);
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

            itemElement.querySelector('.download-btn').addEventListener('click', () => {
                resetProgressBar();
                totalDownloads = 1;
                fetch('/api/download-song', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ track: item })
                })
                .then(response => response.json())
                .then(data => logMessage(data.error || data.message, data.error ? 'error' : 'info'))
                .catch(error => logMessage('Failed to start song download.', 'error'));
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

            itemElement.querySelector('.download-btn').addEventListener('click', async () => {
                resetProgressBar();
                logMessage(`Fetching tracks for album: ${item.title}...`, 'info');
                try {
                    const response = await fetch('/api/get-album-tracks', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ album_id: item.id })
                    });
                    const tracks = await response.json();

                    if (tracks.error) {
                        logMessage(tracks.error, 'error');
                        return;
                    }

                    totalDownloads = tracks.length;
                    logMessage(`Queueing ${totalDownloads} tracks for download...`, 'info');

                    for (const track of tracks) {
                        await new Promise(resolve => setTimeout(resolve, 200));
                        fetch('/api/download-song', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ track: track })
                        });
                    }
                } catch (error) {
                    logMessage('Failed to get album tracks.', 'error');
                }
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
        if (data.type === 'progress') {
            completedDownloads++;
            updateProgressBar();
        } else if (data.type !== 'heartbeat') {
            logMessage(data.message, data.type);
        }
    };
    
    eventSource.onerror = function(err) {
        console.error("EventSource failed:", err);
        logMessage("Connection lost. Reconnecting...", "error");
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
        noMoreResults = true;
    })
    .finally(() => {
        isLoading = false;
    });
}

document.addEventListener('DOMContentLoaded', () => {
    setupEventSource();

    const playlistInput = document.getElementById('playlist-input');
    const startPlaylistBtn = document.getElementById('start-playlist-btn');

    startPlaylistBtn.addEventListener('click', () => {
        const file = playlistInput.files[0];
        if (!file) {
            logMessage('Please select a playlist file.', 'error');
            return;
        }
        resetProgressBar();
        
        const reader = new FileReader();
        reader.onload = function(e) {
            const content = e.target.result;
            const lines = content.split('\n').filter(line => line.includes(' - '));
            totalDownloads = lines.length;

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
});
