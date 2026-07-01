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
    const selectedMode = document.querySelector('input[name="mediaMode"]:checked').value;
    const youtubeUrl = document.getElementById('youtubeUrl').value.trim();
    const fileInput = document.getElementById('mediaFile');

    if (selectedMode === 'youtube' && !youtubeUrl) { alert('กรุณาระบุลิงก์วิดีโอก่อนครับ'); return; }
    if (selectedMode === 'mp4' && fileInput.files.length === 0) { alert('กรุณาเลือกไฟล์วิดีโอก่อนประมวลผล'); return; }

    const modal = document.getElementById('tokenEstimatorModal');
    const statusText = document.getElementById('modal-status-text');
    const calcDetails = document.getElementById('modal-calculation-details');
    const actionsBar = document.getElementById('modalActionsBar');
    
    modal.style.display = 'flex';
    statusText.style.display = 'block';
    statusText.innerText = '🔍 กำลังสแกนตรวจสอบฐานข้อมูลและสารบัญประวัติเก่า...';
    calcDetails.style.display = 'none';
    actionsBar.style.display = 'none';

    const checkForm = new FormData();
    checkForm.append('mode', selectedMode);
    if (selectedMode === 'youtube') {
        checkForm.append('youtube_url', youtubeUrl);
    } else {
        checkForm.append('file_name', fileInput.files[0].name);
        checkForm.append('file_size_bytes', fileInput.files[0].size);
    }

    try {
        const checkRes = await fetch('/pre_check_cache', { method: 'POST', body: checkForm });
        const checkData = await checkRes.json();

        if (checkData.cache_exists) {
            statusText.innerText = '🎯 ตรวจพบประวัติการวิเคราะห์เดิมในเครื่อง! ระบบกำลังโหลดข้อมูลแดชบอร์ดใน 1 วินาที...';
            setTimeout(() => {
                modal.style.display = 'none';
                injectProcessedDataToDashboard(checkData.result_data);
            }, 1200);
            return; 
        }

        statusText.style.display = 'none';
        calcDetails.style.display = 'block';
        actionsBar.style.display = 'flex';

        document.getElementById('est-duration').innerText = checkData.duration_label;
        document.getElementById('est-tokens').innerText = Number(checkData.estimated_tokens).toLocaleString() + ' Tokens';
        document.getElementById('est-cost').innerText = checkData.estimated_cost_baht + ' บาท';

        document.getElementById('btnModalContinue').onclick = function() {
            modal.style.display = 'none';
            proceedWithActualAnalysis(selectedMode, youtubeUrl, fileInput);
        };

        document.getElementById('btnModalCancel').onclick = function() {
            modal.style.display = 'none';
        };

    } catch (err) {
        alert("กระบวนการดักตรวจเช็กข้อมูลล่วงหน้าขัดข้อง");
        modal.style.display = 'none';
    }
}

async function proceedWithActualAnalysis(selectedMode, youtubeUrl, fileInput) {
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

    // รีเซ็ตแผงรายละเอียด
    if (document.getElementById('detail-name')) document.getElementById('detail-name').innerText = "-";
    if (document.getElementById('detail-size')) document.getElementById('detail-size').innerText = "-";
    if (document.getElementById('detail-analysis-time')) document.getElementById('detail-analysis-time').innerText = "กำลังคำนวณ...";
    
    if (keywordBarChartInstance) { keywordBarChartInstance.destroy(); keywordBarChartInstance = null; }
    
    document.getElementById('dominantSentimentBanner').innerText = "📊 การวิเคราะห์มิติสภาวะอารมณ์รวม: อยู่ในระหว่างรอนำเข้าข้อมูล...";
    document.getElementById('sentiment-table-body').innerHTML = `<tr><td colspan="2" style="text-align:center;color:#64748B;">กำลังเรนเดอร์ตารางผลลัพธ์ใหม่...</td></tr>`;
    document.getElementById('recommend-list').innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">กำลังตรวจสอบข้อมูลเชิงสถิติจากเครือข่ายภายนอก...</p>`;
    document.getElementById('chapters-list-container').innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">กำลังจัดสรรสารบัญพิกัดเวลาตามหัวข้อหลัก...</p>`;

    const formData = new FormData();
    formData.append('mode', selectedMode);

    if (selectedMode === 'youtube') {
        formData.append('youtube_url', youtubeUrl);
    } else {
        formData.append('file', fileInput.files[0]);
    }

    const statusBox = document.getElementById('statusBox');
    statusBox.style.display = 'block';
    statusBox.innerText = '🔄 ระบบเริ่มต้นการประสานงานขบวนการประมวลผล: 0%';

    try {
        const response = await fetch('/submit_analysis', { method: 'POST', body: formData });
        const data = await response.json();
        if (data.job_id) { pollJobStatus(data.job_id); } 
        else { statusBox.innerText = `⚡ ดำเนินการประมวลผลสำเร็จรอบด้าน 100%`; injectProcessedDataToDashboard(data); }
    } catch (error) {
        alert("การเชื่อมต่อเครือข่ายปลายทางขัดข้อง");
        statusBox.style.display = 'none';
    }
}

/* 🎯 [ลบตัวซ้ำออกแล้ว]: ฟังก์ชันช่วงเวลา (Time Range Window) แถบส้มจะขยับตามปากพูดเป๊ะๆ ไม่หน่วงตามหลัง */
function trackLiveSubtitle(currentTime) {
    document.getElementById('timeMarker').innerText = `📍 พิกัดเวลาตรวจสอบปัจจุบัน: ${formatToExecutiveTime(currentTime)} นาที`;
    let activeSubText = "🎵 [ ระบบกำลังตรวจสอบความเงียบหรือการประมวลสัญญาณเสียง ]";
    let activeIndex = -1;

    // 🎯 [จุดปลดล็อก]: แอบบวกเวลาเพิ่มเข้าไป 2.5 วินาที (ปรับแต่งตัวเลขนี้ได้ตามความเหมาะสม)
    // เพื่อชดเชยอาการพิกัดเวลาของไฟล์ตัวหนังสือที่หน่วงมาจากหลังบ้าน ส่งผลให้ไฟสีส้มสับดีดลงล่วงหน้าทันใจ
    const adjustedTime = currentTime + 2.5;

    for (let i = 0; i < globalTimelineData.length; i++) {
        // เปลี่ยนมาใช้เวลาที่ปรับแต่งชดเชยความหน่วงแล้ว (adjustedTime) ในการเช็กตัดหน้าแทน
        if (adjustedTime >= globalTimelineData[i].time) {
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
            } else { 
                row.classList.remove('active-row'); 
            }
        });
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


function injectProcessedDataToDashboard(data) {
    const statusBox = document.getElementById('statusBox');
    const rootData = data.result ? data.result : data;
    
    globalTimelineData = rootData.timeline || [];
    originalThaiTextArray = globalTimelineData.map(item => item.text);

    setupMainPlayer(rootData);
    document.getElementById('modelMarker').innerText = '🤖 สถาปัตยกรรม AI ประมวลผล: ' + (rootData.model_used || 'gemini-3.5-flash');
    renderTranscriptComponent(globalTimelineData);

    // อัปเดตข้อมูลรายละเอียด (Box 2)
    const detailName = rootData.media_name || rootData.real_youtube_url || (rootData.video_url ? rootData.video_url.split('/').pop() : "-");
    const detailSize = rootData.file_size_label || "วิเคราะห์จากระบบคลาวด์";
    const detailAnalysisTime = rootData.analysis_time || "โหลดด่วนจากแคชประวัติ (Instant Cached)";

    if (document.getElementById('detail-name')) document.getElementById('detail-name').innerText = detailName;
    if (document.getElementById('detail-size')) document.getElementById('detail-size').innerText = detailSize;
    if (document.getElementById('detail-analysis-time')) document.getElementById('detail-analysis-time').innerText = detailAnalysisTime;

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

    const targetUrl = (data.real_youtube_url || "").toLowerCase();
    const isYoutubeMedia = data.is_youtube && 
                          (targetUrl.includes('youtube.com') || targetUrl.includes('youtu.be')) && 
                          !targetUrl.includes('tiktok.com');

    if (isYoutubeMedia) {
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
        videoTag.autoplay = true; 
        videoTag.style.width = '100%';
        videoTag.style.height = '100%';
        videoTag.style.borderRadius = '8px';
        videoTag.style.display = 'block';
        
        videoTag.src = data.video_url; 
        wrapper.appendChild(videoTag);
        
        videoTag.ontimeupdate = function() { 
            trackLiveSubtitle(videoTag.currentTime); 
        };
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

// ล้างคอมเมนต์เพื่อความสากล
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
    
    if (!chapters || chapters.length === 0) {
        container.innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">ไม่พบโครงสร้างแบ่งแยกส่วนข้อมูลย่อยในสื่อนี้</p>`;
        return;
    }
    
    const uniqueChapters = [...new Map(chapters.map(item => [item.chapter_title, item])).values()];
    
    uniqueChapters.forEach(ch => {
        const accordionDetails = document.createElement('details');
        accordionDetails.className = 'chapter-accordion-box';

        const accordionSummary = document.createElement('summary');
        accordionSummary.className = 'chapter-summary-bar';
        
        accordionSummary.innerHTML = `
            <div class="summary-left-content">
                <span class="main-chapter-time">⏱️ ${ch.time_range_label}</span>
                <span class="main-chapter-title">${ch.chapter_title}</span>
            </div>
            <span class="toggle-icon-indicator">▼</span>
        `;
        
        accordionSummary.addEventListener('click', (e) => {
            warpToTargetTime(ch.start_time_seconds);
        });

        accordionDetails.addEventListener('toggle', function(e) {
            if (accordionDetails.open) {
                const allAccordions = container.querySelectorAll('.chapter-accordion-box');
                allAccordions.forEach(otherBox => {
                    if (otherBox !== accordionDetails) {
                        otherBox.removeAttribute('open');
                    }
                });
            }
        });

        accordionDetails.appendChild(accordionSummary);

        if (ch.sub_chapters && ch.sub_chapters.length > 0) {
            const subChaptersWrapper = document.createElement('div');
            subChaptersWrapper.className = 'sub-chapters-dropdown-container';

            ch.sub_chapters.forEach(sub => {
                const subItemCard = document.createElement('div');
                subItemCard.className = 'sub-chapter-node-item';
                subItemCard.innerHTML = `
                    <span class="sub-node-time">📌 ${sub.time_range_label}</span>
                    <span class="sub-node-text">${sub.sub_title}</span>
                `;
                
                subItemCard.onclick = (e) => {
                    e.stopPropagation(); 
                    warpToTargetTime(sub.start_time_seconds);
                };
                
                subChaptersWrapper.appendChild(subItemCard);
            });
            accordionDetails.appendChild(subChaptersWrapper);
        } else {
            const noSubWrapper = document.createElement('div');
            noSubWrapper.className = 'sub-chapters-dropdown-container';
            noSubWrapper.innerHTML = `<div style="color:#64748B; font-size:12px; padding: 5px 15px;">🔍 ไม่พบหัวข้อย่อยสำหรับบทเรียนหลักนี้</div>`;
            accordionDetails.appendChild(noSubWrapper);
        }
        
        container.appendChild(accordionDetails);
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