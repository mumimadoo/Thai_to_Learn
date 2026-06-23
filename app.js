let globalTimelineData = [];
let originalThaiTextArray = [];
let keywordBarChartInstance = null;
let activeYtPlayer = null;
let ytTimerInterval = null;

function toggleInputFields() {
    const mode = document.querySelector('input[name="mediaMode"]:checked').value;
    document.getElementById('youtubeInputWrapper').style.display = (mode === 'youtube') ? 'flex' : 'none';
    document.getElementById('fileInputWrapper').style.display = (mode === 'youtube') ? 'none' : 'flex';
}

function executeModuleSwitch() {
    const selectedValue = document.getElementById('mainDashboardSelector').value;
    document.querySelectorAll('.module-view').forEach(view => { view.classList.remove('active'); });
    const targetModule = document.getElementById('module-' + selectedValue);
    if (targetModule) { targetModule.classList.add('active'); }
}

function formatToExecutiveTime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
    const secs = Math.floor(totalSeconds % 60).toString().padStart(2, '0');
    return `${minutes}:${secs}`;
}

// 🎯 ฟังก์ชันเช็กสถานะเปอร์เซ็นต์ทีละสเต็ป (Polling Loop) ป้องกันหน้าจอหลุดค้างถาวร
function pollJobStatus(jobId) {
    const statusBox = document.getElementById('statusBox');
    
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/job_status/${jobId}`);
            const job = await res.json();
            
            if (job.status === "processing") {
                // อัปเดตขึ้นเปอร์เซ็นต์เพียว ๆ ดิบ ๆ ตามใจคุณ PookPiK ทันที
                statusBox.innerText = `⚙️ กำลังประมวลผลคลิปยาวอย่างละเอียด: ${job.progress}%`;
                document.getElementById('transcript-list').innerHTML = `<p style="color:#F39C12;text-align:center;padding-top:40px;">⏳ ดำเนินงานแกะสถิติตามระบบคิวแยกสายภาพและเสียง... ดำเนินการแล้ว ${job.progress}%</p>`;
            } 
            else if (job.status === "completed") {
                clearInterval(interval);
                statusBox.innerText = `⚙️ กำลังประมวลผลคลิปยาวอย่างละเอียด: 100%`;
                // เรนเดอร์แพ็กเกจข้อมูลเข้าสู่โมดูลหลัก
                injectProcessedDataToDashboard(job.result);
            } 
            else if (job.status === "failed") {
                clearInterval(interval);
                alert("เกิดข้อผิดพลาดคลังคิว: " + job.error);
                statusBox.style.display = 'none';
            }
        } catch (e) {
            clearInterval(interval);
            alert("ขาดการเชื่อมต่อสายรายงานสถานะเปอร์เซ็นต์");
            statusBox.style.display = 'none';
        }
    }, 2500); // วิ่งมาเช็กสถานะหลังบ้านทุก 2.5 วินาที
}

async function uploadAndProcessData() {
    globalTimelineData = [];
    originalThaiTextArray = [];
    
    document.getElementById('transcript-list').innerHTML = `<p style="color:#F39C12;text-align:center;padding-top:40px;">⏳ ดำเนินการฟังเสียงแท้ แกะคำต่อคำ และคำนวณฐานสถิติ 8 โมดูล... กรุณารอสักครู่</p>`;
    document.getElementById('pivotLanguageSelect').value = "TH";
    document.getElementById('live-sub-box').innerText = "🎵 [ ระบบกำลังเริ่มประมวลผลวิดีโอใหม่... ]";
    document.getElementById('summary-list').innerHTML = `<p style="color:#6A7280;">กำลังสกัดโครงสร้างข้อสรุปใหม่...</p>`;
    
    document.getElementById('t-duration').innerText = "-";
    document.getElementById('t-words').innerText = "-";
    document.getElementById('t-sentences').innerText = "-";
    document.getElementById('t-wpm').innerText = "-";
    document.getElementById('t-topics').innerText = "-";
    
    if (keywordBarChartInstance) { keywordBarChartInstance.destroy(); keywordBarChartInstance = null; }
    
    document.getElementById('dominantSentimentBanner').innerText = "📊 บทวิเคราะห์แก่นบรรยากาศรวม: กำลังวิเคราะห์คลิปใหม่...";
    document.getElementById('sentiment-table-body').innerHTML = `<tr><td colspan="2" style="text-align:center;color:#6A7280;">กำลังเรนเดอร์ตารางอารมณ์ใหม่...</td></tr>`;
    document.getElementById('recommend-list').innerHTML = `<p style="text-align:center;color:#6A7280;width:100%;">กำลังค้นหาคลิปแนะนำใหม่จาก YouTube...</p>`;
    document.getElementById('chapters-list-container').innerHTML = `<p style="text-align:center;color:#6A7280;width:100%;">กำลังจำแนกบทเรียนช่วงเวลาใหม่...</p>`;

    const selectedMode = document.querySelector('input[name="mediaMode"]:checked').value;
    const formData = new FormData();
    formData.append('mode', selectedMode);

    if (selectedMode === 'youtube') {
        let url = document.getElementById('youtubeUrl').value.trim();
        if (!url) { alert('กรุณาระบุลิงก์วิดีโอก่อนครับ'); return; }
        
        if (url.includes('<blockquote') || url.includes('tiktok-embed')) {
            const urlMatch = url.match(/cite=["'](https:\/\/[^"']+)["']/);
            if (urlMatch && urlMatch[1]) {
                url = urlMatch[1];
                document.getElementById('youtubeUrl').value = url;
            } else {
                const directUrlMatch = url.match(/(https:\/\/www\.tiktok\.com\/@[^\s"'><]+)/);
                if (directUrlMatch && directUrlMatch[1]) {
                    url = directUrlMatch[1];
                    document.getElementById('youtubeUrl').value = url;
                }
            }
        }
        formData.append('youtube_url', url);
    } else {
        const fileInput = document.getElementById('mediaFile');
        if (fileInput.files.length === 0) { alert('กรุณาเลือกไฟล์ก่อนครับ'); return; }
        formData.append('file', fileInput.files[0]);
    }

    const statusBox = document.getElementById('statusBox');
    statusBox.style.display = 'block';
    statusBox.innerText = '⚙️ กำลังประมวลผลคลิปยาวอย่างละเอียด: 0%';

    try {
        const response = await fetch('/process', { method: 'POST', body: formData });
        const data = await response.json();
        
        if (data.error) { alert('เกิดข้อผิดพลาด: ' + data.error); statusBox.style.display = 'none'; return; }

        // ถ้าระบบโยนกลับมาเป็นแบบ Cache Hit (ดึงข้อมูลเก่าทันที)
        if (!data.queued) {
            statusBox.innerText = `⚙️ กำลังประมวลผลคลิปยาวอย่างละเอียด: 100%`;
            injectProcessedDataToDashboard(data);
        } else {
            // ถ้าระบบโยนเข้าคิว Background ให้สั่งเข้าลูปดักเช็กสถานะและพิมพ์ % วิ่งบนหน้าจอ
            pollJobStatus(data.job_id);
        }

    } catch (error) {
        alert('การเชื่อมต่อล้มเหลว: ' + error);
        statusBox.style.display = 'none';
    }
}

// ฟังก์ชันฉีดผลลัพธ์ลงกระดานเรนเดอร์ของ 8 โมดูลดั้งเดิม ปลอดภัย ไร้กังวล
function injectProcessedDataToDashboard(data) {
    const statusBox = document.getElementById('statusBox');
    globalTimelineData = data.timeline;
    originalThaiTextArray = data.timeline.map(item => item.text);

    setupMainPlayer(data);
    document.getElementById('modelMarker').innerText = '🤖 โมเดลใช้งาน: ' + data.model_used;
    renderTranscriptComponent(globalTimelineData);

    let summaryHtml = '<ul>';
    data.summary.forEach(item => { summaryHtml += `<li>${item}</li>`; });
    summaryHtml += '</ul>';
    document.getElementById('summary-list').innerHTML = summaryHtml;

    document.getElementById('t-duration').innerText = data.telemetry.duration;
    document.getElementById('t-words').innerText = data.telemetry.words;
    document.getElementById('t-sentences').innerText = data.telemetry.sentences;
    document.getElementById('t-wpm').innerText = `${data.telemetry.wpm} คำ/นาที`;
    document.getElementById('t-topics').innerText = data.telemetry.topics;

    drawKeywordBarChart(data.keywords_chart);
    renderSentimentModule(data.sentiment_table, data.dominant_sentiment);
    renderRecommendations(data.recommendations);
    renderVideoChaptersModule(data.video_chapters);

    statusBox.style.display = 'none';
    document.getElementById('mainDashboardSelector').value = "transcript";
    executeModuleSwitch();
}

function trackLiveSubtitle(currentTime) {
    document.getElementById('timeMarker').innerText = `📍 พิกัดเวลารับชมปัจจุบัน: ${formatToExecutiveTime(currentTime)} นาที`;
    let activeSubText = "🎵 [ ช่วงทำนองเสียงหรือภาพประกอบเนื้อหา ]";
    let activeIndex = -1;

    for (let i = 0; i < globalTimelineData.length; i++) {
        if (currentTime >= globalTimelineData[i].time) {
            activeSubText = globalTimelineData[i].label + " " + globalTimelineData[i].text;
            activeIndex = i;
        } else {
            break;
        }
    }
    document.getElementById('live-sub-box').innerText = activeSubText;

    if (activeIndex !== -1) {
        document.querySelectorAll('.transcript-row').forEach((row, idx) => {
            if (idx === activeIndex) {
                if (!row.classList.contains('active-row')) {
                    row.classList.add('active-row');
                    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            } else { row.classList.remove('active-row'); }
        });
    }
}

function renderVideoChaptersModule(chapters) {
    const container = document.getElementById('chapters-list-container');
    container.innerHTML = '';
    if (!chapters || chapters.length === 0) {
        container.innerHTML = `<p style="text-align:center;color:#6A7280;width:100%;">คลิปสั้นเกินไปหรือเนื้อหาเป็นเอกเทศชิ้นเดียว AI จึงไม่ได้แบ่งท่อนสารบัญย่อย</p>`;
        return;
    }
    chapters.forEach(ch => {
        const card = document.createElement('div');
        card.className = 'chapter-card-item';
        card.setAttribute('onclick', `warpToTargetTime(${ch.start_time_seconds})`);
        card.innerHTML = `<div class="chapter-time-block">⏱️ ${ch.time_range_label}</div><div class="chapter-text-block">${ch.chapter_title}</div>`;
        container.appendChild(card);
    });
}

function renderTranscriptComponent(items, keyword = "") {
    const listContainer = document.getElementById('transcript-list');
    if (items.length === 0) { listContainer.innerHTML = `<p style="color:#6A7280;text-align:center;">ไม่พบข้อมูลประโยค</p>`; return; }
    let innerHtml = '';
    items.forEach((row, index) => {
        let txt = row.text;
        if (keyword) {
            const regex = new RegExp(`(${keyword})`, "gi");
            txt = txt.replace(regex, "<mark>$1</mark>");
        }
        innerHtml += `<div class="transcript-row" id="tx-row-${index}"><button class="time-badge" onclick="warpToTargetTime(${row.time})">${row.label}</button><div class="phrase-box" onclick="warpToTargetTime(${row.time})">${txt}</div></div>`;
    });
    listContainer.innerHTML = innerHtml;
}

function warpToTargetTime(seconds) {
    const nativePlayer = document.querySelector('.player-wrapper video');
    if (nativePlayer) { nativePlayer.currentTime = seconds; nativePlayer.play(); }
    else if (activeYtPlayer && activeYtPlayer.seekTo) { activeYtPlayer.seekTo(seconds, true); activeYtPlayer.playVideo(); }
}

function setupMainPlayer(data) {
    const wrapper = document.getElementById('playerWrapper');
    clearInterval(ytTimerInterval);
    wrapper.innerHTML = ''; 

    if (data.is_youtube && data.real_youtube_url) {
        let videoId = 'dQw4w9WgXcQ';
        try {
            if (data.real_youtube_url.includes('youtu.be/')) {
                videoId = data.real_youtube_url.split('youtu.be/')[1].split('?')[0];
            } else if (data.real_youtube_url.includes('v=')) {
                const urlObj = new URL(data.real_youtube_url);
                videoId = urlObj.searchParams.get('v');
            }
        } catch (e) {}

        const divTarget = document.createElement('div');
        divTarget.id = 'ytActualPlayer';
        wrapper.appendChild(divTarget);

        activeYtPlayer = new YT.Player('ytActualPlayer', {
            height: '100%', width: '100%', videoId: videoId,
            playerVars: { 'rel': 0, 'modestbranding': 1, 'origin': window.location.origin },
            events: {
                'onReady': function() {
                    ytTimerInterval = setInterval(() => {
                        // 🎯 ปรับจุดนี้: ตรวจสอบแบบรัดกุมว่าวัตถุมีฟังก์ชันดึงเวลาจริง ๆ ไหม ก่อนจะสั่งให้มันทำงาน
                        if (activeYtPlayer && typeof activeYtPlayer.getCurrentTime === 'function') {
                            trackLiveSubtitle(activeYtPlayer.getCurrentTime());
                        }
                    }, 300);
                }
            }
        });
    } else {
        activeYtPlayer = null;
        const videoTag = document.createElement('video');
        videoTag.controls = true; 
        videoTag.style.width = '100%';
        videoTag.style.height = '100%';
        videoTag.src = data.video_url; 
        wrapper.appendChild(videoTag);
        videoTag.ontimeupdate = function() { trackLiveSubtitle(videoTag.currentTime); };
    }
}

function filterTranscriptData() {
    const kw = document.getElementById('searchKeyword').value.trim();
    if (!kw) { renderTranscriptComponent(globalTimelineData); return; }
    const filtered = globalTimelineData.filter(item => item.text.toLowerCase().includes(kw.toLowerCase()));
    renderTranscriptComponent(filtered, kw);
}

function renderSentimentModule(list, dominantSummary) {
    const tbody = document.getElementById('sentiment-table-body');
    tbody.innerHTML = '';
    document.getElementById('dominantSentimentBanner').innerText = `📊 บทวิเคราะห์แก่นบรรยากาศรวมโดย AI: ${dominantSummary}`;
    if (!list || list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;">ไม่พบข้อมูลอารมณ์</td></tr>`;
        return;
    }
    list.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${row.time_range}</td><td>${row.sentiment}</td>`;
        tbody.appendChild(tr);
    });
}

function drawKeywordBarChart(chartData) {
    const ctx = document.getElementById('keywordBarChart').getContext('2d');
    if (keywordBarChartInstance) keywordBarChartInstance.destroy();
    const limitedData = chartData.slice(0, 5);
    keywordBarChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: limitedData.map(item => item.keyword),
            datasets: [{ label: 'ความถี่การตรวจพบคำสำคัญประจำคลิป', data: limitedData.map(item => item.count), backgroundColor: '#F39C12', borderColor: '#F1C40F', borderWidth: 1 }]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { ticks: { color: '#8A94A6' }, grid: { color: '#232A36' } }, x: { ticks: { color: '#EDF0F5' }, grid: { display: false } } }, plugins: { legend: { labels: { color: '#FFF', font: { family: 'Sarabun' } } } } }
    });
}

function renderRecommendations(cards) {
    const container = document.getElementById('recommend-list');
    container.innerHTML = '';
    if (!cards || cards.length === 0) { container.innerHTML = `<p style="color:#6A7280;text-align:center;">ไม่มีคลิปแนะนำ</p>`; return; }
    cards.forEach((card, index) => {
        const rowDiv = document.createElement('div');
        rowDiv.className = 'recommend-row-item';
        rowDiv.innerHTML = `<div class="recommend-row-title">${index + 1}. ${card.title}</div><a href="${card.url}" target="_blank" class="recommend-cover-link"><img src="${card.thumbnail}" class="recommend-cover-img"></a>`;
        container.appendChild(rowDiv);
    });
}

async function executePivotTranslation() {
    let lang = document.getElementById('pivotLanguageSelect').value;
    if (originalThaiTextArray.length === 0) return;
    if (lang === "TH") { globalTimelineData.forEach((item, idx) => { item.text = originalThaiTextArray[idx]; }); renderTranscriptComponent(globalTimelineData); return; }
    
    document.getElementById('transcript-list').innerHTML = `<p style="color:#F1C40F;text-align:center;padding-top:40px;">🌐 ระบบกำลังแปลภาษาปลายทาง...</p>`;
    const fData = new FormData(); 
    fData.append('target_lang', lang); 
    fData.append('transcript_text', originalThaiTextArray.join("\n"));

    try {
        const res = await fetch('/translate_timeline', { method: 'POST', body: fData });
        const resData = await res.json();
        if (resData.translated_lines) { globalTimelineData.forEach((item, idx) => { item.text = resData.translated_lines[idx] || item.text; }); renderTranscriptComponent(globalTimelineData); }
    } catch (e) { alert(e); }
}