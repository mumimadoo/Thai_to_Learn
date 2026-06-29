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

function pollJobStatus(jobId) {
    const statusBox = document.getElementById('statusBox');
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/job_status/${jobId}`);
            const job = await res.json();
            
            if (job.status === "processing" || job.status === "queued") {
                statusBox.innerText = `🔄 ระบบกำลังดำเนินการคัดกรอง แยกสัญญาณ และวิเคราะห์ฐานข้อมูลขั้นสูง... ${job.progress || 0}%`;
                document.getElementById('transcript-list').innerHTML = `<p style="color:#FF9800;text-align:center;padding-top:40px;">⏳ ระบบกำลังดำเนินงานสกัดสถิติตามขบวนการ Pipeline แยกภาพและเสียง... ${job.progress || 0}%</p>`;
            } 
            else if (job.status === "completed") {
                clearInterval(interval);
                statusBox.innerText = `⚡ ดำเนินการประมวลผลสำเร็จรอบด้าน 100%`;
                injectProcessedDataToDashboard(job.result);
            } 
            else if (job.status === "failed") {
                clearInterval(interval);
                alert("เกิดข้อผิดพลาดในการประมวลผลระบบคิว: " + job.error);
                statusBox.style.display = 'none';
            }
        } catch (e) {
            clearInterval(interval);
            statusBox.style.display = 'none';
        }
    }, 2500);
}

async function uploadAndProcessData() {
    globalTimelineData = [];
    originalThaiTextArray = [];
    
    document.getElementById('transcript-list').innerHTML = `<p style="color:#FF9800;text-align:center;padding-top:40px;">⏳ กำลังเรียกใช้โครงสร้างวิเคราะห์ 8 โมดูลหลัก... กรุณารอสักครู่</p>`;
    document.getElementById('pivotLanguageSelect').value = "TH";
    document.getElementById('live-sub-box').innerText = "🎵 [ ระบบกำลังเริ่มประมวลผลวิดีโอใหม่... ]";
    document.getElementById('summary-list').innerHTML = `<p style="color:#64748B;">กำลังดำเนินการถอดความและคัดกรองประเด็นยุทธศาสตร์...</p>`;
    
    document.getElementById('t-duration').innerText = "-";
    document.getElementById('t-words').innerText = "-";
    document.getElementById('t-sentences').innerText = "-";
    document.getElementById('t-wpm').innerText = "-";
    document.getElementById('t-topics').innerText = "-";
    
    if (keywordBarChartInstance) { keywordBarChartInstance.destroy(); keywordBarChartInstance = null; }
    
    document.getElementById('dominantSentimentBanner').innerText = "📊 การวิเคราะห์มิติสภาวะอารมณ์รวม: อยู่ในระหว่างรอนำเข้าข้อมูล...";
    document.getElementById('sentiment-table-body').innerHTML = `<tr><td colspan="2" style="text-align:center;color:#64748B;">กำลังเรนเดอร์ตารางผลลัพธ์ใหม่...</td></tr>`;
    document.getElementById('recommend-list').innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">กำลังตรวจสอบข้อมูลเชิงสถิติจากเครือข่ายภายนอก...</p>`;
    document.getElementById('chapters-list-container').innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">กำลังจัดสรรสารบัญพิกัดเวลาตามหัวข้อหลัก...</p>`;

    const selectedMode = document.querySelector('input[name="mediaMode"]:checked').value;
    const formData = new FormData();
    
    formData.append('mode', selectedMode);

    if (selectedMode === 'youtube') {
        let url = document.getElementById('youtubeUrl').value.trim();
        if (!url) { alert('กรุณาระบุลิงก์วิดีโอก่อนครับ'); return; }
        formData.append('youtube_url', url);
    } else {
        const fileInput = document.getElementById('mediaFile');
        if (fileInput.files.length === 0) { alert('กรุณาเลือกไฟล์ภาพหรือเสียงก่อนประมวลผล'); return; }
        formData.append('file', fileInput.files[0]);
    }

    const statusBox = document.getElementById('statusBox');
    statusBox.style.display = 'block';
    statusBox.innerText = '🔄 ระบบเริ่มต้นการประสานงานขบวนการประมวลผล: 0%';

    try {
        const response = await fetch('/submit_analysis', { method: 'POST', body: formData });
        const data = await response.json();
        
        if (data.job_id) {
            pollJobStatus(data.job_id);
        } else {
            statusBox.innerText = `⚡ ประมวลผลสำเร็จเสร็จสิ้น`;
            injectProcessedDataToDashboard(data);
        }
    } catch (error) {
        alert("การเชื่อมต่อเครือข่ายปลายทางขัดข้อง");
        statusBox.style.display = 'none';
    }
}

function injectProcessedDataToDashboard(data) {
    const statusBox = document.getElementById('statusBox');
    const rootData = data.result ? data.result : data;
    
    globalTimelineData = rootData.timeline || [];
    originalThaiTextArray = globalTimelineData.map(item => item.text);

    setupMainPlayer(rootData);
    document.getElementById('modelMarker').innerText = '🤖 สถาปัตยกรรม AI ประมวลผล: ' + (rootData.model_used || 'gemini-3.5-flash');
    renderTranscriptComponent(globalTimelineData);

    let summaryHtml = '<ul>';
    if (rootData.summary && rootData.summary.length > 0) {
        rootData.summary.forEach(item => { summaryHtml += `<li>${item}</li>`; });
    } else {
        summaryHtml += `<li>สกัดย่อโครงสร้างความเรียบร้อยเสร็จสิ้นตามระบบ</li>`;
    }
    summaryHtml += '</ul>';
    document.getElementById('summary-list').innerHTML = summaryHtml;

    if (rootData.telemetry) {
        document.getElementById('t-duration').innerText = rootData.telemetry.duration || "-";
        document.getElementById('t-words').innerText = rootData.telemetry.words || "-";
        document.getElementById('t-sentences').innerText = rootData.telemetry.sentences || "-";
        document.getElementById('t-wpm').innerText = rootData.telemetry.wpm ? `${rootData.telemetry.wpm} คำ/นาที` : "-";
        document.getElementById('t-topics').innerText = rootData.telemetry.topics || "-";
    }

    if (rootData.keywords_chart) drawKeywordBarChart(rootData.keywords_chart);
    renderSentimentModule(rootData.sentiment_table || [], rootData.dominant_sentiment || "วิเคราะห์สถิติจิตวิทยาสำเร็จ");
    renderRecommendations(rootData.recommendations || []);
    renderVideoChaptersModule(rootData.video_chapters || []);

    statusBox.style.display = 'none';
    document.getElementById('mainDashboardSelector').value = "transcript";
    executeModuleSwitch();
}

function trackLiveSubtitle(currentTime) {
    document.getElementById('timeMarker').innerText = `📍 พิกัดเวลาตรวจสอบปัจจุบัน: ${formatToExecutiveTime(currentTime)} นาที`;
    let activeSubText = "🎵 [ ระบบกำลังตรวจสอบความเงียบหรือการประมวลสัญญาณเสียง ]";
    let activeIndex = -1;

    for (let i = 0; i < globalTimelineData.length; i++) {
        if (currentTime >= globalTimelineData[i].time) {
            activeSubText = globalTimelineData[i].label + " " + globalTimelineData[i].text;
            activeIndex = i;
        } else { break; }
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

function renderTranscriptComponent(items, keyword = "") {
    const listContainer = document.getElementById('transcript-list');
    if (items.length === 0) { listContainer.innerHTML = `<p style="color:#64748B;text-align:center;">ไม่พบชุดข้อความที่ตรงตามเงื่อนไขการค้นหา</p>`; return; }
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
    document.getElementById('dominantSentimentBanner').innerText = `📊 การวิเคราะห์มิติสภาวะอารมณ์รวม: ${dominantSummary}`;
    if (!list || list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;">ไม่พบคลิปข้อมูลแจกแจงมิติเชิงจิตวิทยาในตาราง</td></tr>`;
        return;
    }
    list.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="vertical-align:top;width:25%; color:#FF9800;">${row.time_range}</td>
            <td>
                <div style="font-size:15px;color:#E2E8F0;margin-bottom:4px;">${row.sentiment}</div>
                <div style="font-size:12px;color:#64748B;margin-bottom:2px;">${row.trigger}</div>
                <div style="font-size:12px;color:#FF5722;">${row.purpose}</div>
            </td>`;
        tbody.appendChild(tr);
    });
}

// แผนภูมิ
function drawKeywordBarChart(chartData) {
    const ctx = document.getElementById('keywordBarChart').getContext('2d');
    if (keywordBarChartInstance) keywordBarChartInstance.destroy();
    const limitedData = chartData.slice(0, 5);
    keywordBarChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: limitedData.map(item => item.keyword),
            datasets: [{ label: 'อัตราความถี่ความหนาแน่นของการตรวจพบคำสำคัญ', data: limitedData.map(item => item.count), backgroundColor: '#FF5722', borderColor: '#FF9800', borderWidth: 1 }]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { ticks: { color: '#64748B' }, grid: { color: '#2A2F3A' } }, x: { ticks: { color: '#E2E8F0' }, grid: { display: false } } }, plugins: { legend: { labels: { color: '#FFF', font: { family: 'Sarabun' } } } } }
    });
}

function renderRecommendations(cards) {
    const container = document.getElementById('recommend-list');
    container.innerHTML = '';
    if (!cards || cards.length === 0) { container.innerHTML = `<p style="color:#64748B;text-align:center;">ไม่พบผลลัพธ์สื่อความใกล้เคียงที่เกี่ยวข้องในฐานระบบ</p>`; return; }
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
    
    document.getElementById('transcript-list').innerHTML = `<p style="color:#FF9800;text-align:center;padding-top:40px;">🌐 ระบบกำลังส่งสัญญาณแปลชุดโครงสร้างภาษาปลายทางไปยังโครงข่าย AI...</p>`;
    const fData = new FormData(); 
    fData.append('target_lang', lang); 
    fData.append('transcript_text', originalThaiTextArray.join("\n"));

    try {
        const res = await fetch('/translate_timeline', { method: 'POST', body: fData });
        const resData = await res.json();
        if (resData.translated_lines) { globalTimelineData.forEach((item, idx) => { item.text = resData.translated_lines[idx] || item.text; }); renderTranscriptComponent(globalTimelineData); }
    } catch (e) { alert("กระบวนการแปลชุดภาษาขัดข้องในโครงข่ายย่อย"); }
}

function renderVideoChaptersModule(chapters) {
    const container = document.getElementById('chapters-list-container');
    container.innerHTML = '';
    if (!chapters || chapters.length === 0) return;
    const unique = [...new Map(chapters.map(item => [item.chapter_title, item])).values()];
    unique.forEach(ch => {
        const item = document.createElement('div');
        item.className = 'chapter-card-item';
        item.innerHTML = `<span style="color:#FF9800; margin-right:10px;">⏱️ ${ch.time_range_label}</span> <span>${ch.chapter_title}</span>`;
        item.onclick = () => warpToTargetTime(ch.start_time_seconds);
        container.appendChild(item);
    });
}

function warpToTargetTime(seconds) {
    const player = document.querySelector('video') || (activeYtPlayer ? activeYtPlayer : null);
    const wrapper = document.querySelector('.sticky-player-box');
    
    if (wrapper) {
        wrapper.style.transition = "box-shadow 0.2s ease";
        wrapper.style.boxShadow = "0 0 35px rgba(255, 87, 34, 0.8)";
        setTimeout(() => { wrapper.style.boxShadow = "0 15px 35px rgba(0,0,0,0.6)"; }, 500);
    }
    
    if (player && player.seekTo) player.seekTo(seconds, true);
    else if (player) player.currentTime = seconds;
}