let globalTimelineData = [];
let originalThaiTextArray = [];
let globalKeywordsChartData = [];
let keywordBarChartInstance = null;
let activeYtPlayer = null;
let ytTimerInterval = null;
let globalCommunicationIntervals = [];
let activeCommunicationRow = null;
let lastCommunicationIndex = -1;

// --- 🌞/🌙 ระบบสลับธีมรักษาพลังงานและการส่องสว่าง ---
function initTheme() {
    const themeCheckbox = document.getElementById('themeCheckbox');
    const savedTheme = localStorage.getItem('theme') || 'dark'; // เริ่มต้นที่ Dark Mode ตามความสวยงามคลาสสิกของแอปเดิม
    
    document.documentElement.setAttribute('data-theme', savedTheme);
    if (themeCheckbox) {
        themeCheckbox.checked = (savedTheme === 'dark');
        
        themeCheckbox.addEventListener('change', () => {
            const newTheme = themeCheckbox.checked ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            
            // เรนเดอร์กราฟใหม่ให้สีแกนและฉลากกลมกลืนตามธีมล่าสุดทันที
            if (globalKeywordsChartData && globalKeywordsChartData.length > 0) {
                drawKeywordBarChart(globalKeywordsChartData);
            }
        });
    }
}

// โหลดระบบสลับธีมทันที (พยายามเปิดก่อน หรือรอ DOMContentLoaded เพื่อความมั่นใจสูงสุด)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTheme);
} else {
    initTheme();
}

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

        const durationSeconds = checkData.duration_seconds || 300;

        document.getElementById('est-duration').innerText = checkData.duration_label;
        
        // Dynamic Estimation recalculation function
        window.recalculateEstimation = function(secs) {
            const modelSelect = document.getElementById('estimatorModelSelect');
            if (!modelSelect) return;
            const selectedModel = modelSelect.value;
            
            // 🎯 [จุดสำคัญ]: เปลี่ยนมาใช้ Math.ceil เพื่อปัดเศษวินาทีขึ้นเป็นนาทีเต็มทันที
            let durationMinutes = Math.ceil(secs / 60.0);
            if (isNaN(durationMinutes) || durationMinutes < 1) {
                durationMinutes = 1;
            }
            
            // 🎯 1. ตั้งต้นจำนวน Tokens ตามสูตรใหม่ที่สมเหตุสมผลกว่า
            const totalInputTokens = Math.ceil(durationMinutes * 3000);
            const totalOutputTokens = 2500; // ค่าคงที่สำหรับคำตอบ JSON 8 โมดูล
            const totalTokensCombined = totalInputTokens + totalOutputTokens;
            
            // 🎯 2. กำหนดราคาต่อ 1 ล้าน Tokens ของแต่ละรุ่น (หน่วยเป็น USD) - ปรับปรุงให้ตรงโครงสร้างราคาปัจจุบัน
            let inputRateUSD = 0.05;   // ราคาฐานของ Gemini 2.5 Flash
            let outputRateUSD = 0.20;
            
            if (selectedModel === 'gemini-3.5-flash') {
                inputRateUSD = 0.075;
                outputRateUSD = 0.30;
            } else if (selectedModel === 'gemini-2.5-flash-lite') {
                inputRateUSD = 0.025;
                outputRateUSD = 0.10;
            }
            
            // 🎯 3. แยกคำนวณเงินดอลลาร์ ของแต่ละฝั่ง
            const inputCostUSD = (totalInputTokens * inputRateUSD) / 1000000;
            const outputCostUSD = (totalOutputTokens * outputRateUSD) / 1000000;
            
            // 🎯 4. แปลงเป็นเงินบาท (อิงเรท 35 บาท)
            const inputCostBaht = inputCostUSD * 35;
            const outputCostBaht = outputCostUSD * 35;
            
            // 🎯 5. รวมค่าบริการจาก API + บวกรวมค่ารันเซิร์ฟเวอร์หนัก
            const serverBaseFee = 1.50; // ปรับค่าบริการเซิร์ฟเวอร์เหลือ 1.50 บาทให้สมเหตุสมผล
            const finalCostBaht = inputCostBaht + outputCostBaht + serverBaseFee;
            
            // 🎯 6. พ่นตัวเลขขึ้นหน้าจอ Modal
            document.getElementById('est-tokens').innerText = totalTokensCombined.toLocaleString() + ' Tokens';
            document.getElementById('est-cost').innerText = finalCostBaht.toFixed(2) + ' บาท';
        };

        // Initial real-time estimation
        window.recalculateEstimation(durationSeconds);

        // Bind model selection change event
        const modelSelect = document.getElementById('estimatorModelSelect');
        if (modelSelect) {
            modelSelect.onchange = function() {
                window.recalculateEstimation(durationSeconds);
            };
        }

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
    
    document.getElementById('transcript-list').innerHTML = `<p style="color:#FF9800;text-align:center;padding-top:40px;">⏳ กำลังเรียกใช้โครงสร้างวิเคราะห์ 9 โมดูลหลัก... กรุณารอสักครู่</p>`;
    document.getElementById('pivotLanguageSelect').value = "TH";
    document.getElementById('live-sub-box').innerText = "🎵 [ ระบบกำลังเริ่มประมวลผลวิดีโอใหม่... ]";
    document.getElementById('summary-list').innerHTML = `<p style="color:#64748B;">กำลังดำเนินการถอดความและคัดกรองประเด็นยุทธศาสตร์...</p>`;
    
    document.getElementById('t-duration').innerText = "-";
    document.getElementById('t-words').innerText = "-";
    document.getElementById('t-sentences').innerText = "-";
    document.getElementById('t-wpm').innerText = "-";
    if (document.getElementById('t-topics')) document.getElementById('t-topics').innerText = "-";

    // รีเซ็ตแผงรายละเอียด
    if (document.getElementById('detail-name')) document.getElementById('detail-name').innerText = "-";
    if (document.getElementById('detail-size')) document.getElementById('detail-size').innerText = "-";
    if (document.getElementById('detail-analysis-time')) document.getElementById('detail-analysis-time').innerText = "กำลังคำนวณ...";
    
    if (keywordBarChartInstance) { keywordBarChartInstance.destroy(); keywordBarChartInstance = null; }
    
    const moodBadge =
        document.getElementById("currentMoodBadge");

    if (moodBadge) {
        moodBadge.textContent =
            "⚪ อารมณ์ปัจจุบัน: ไม่ระบุ";
    }

    const videoMoodBadge =
        document.getElementById("videoCurrentMoodBadge");

    if (videoMoodBadge) {
        videoMoodBadge.textContent =
            "⚪ อารมณ์ปัจจุบัน: ไม่ระบุ";
    }

    const summaryBox =
        document.getElementById(
            "communication-emotion-summary"
        );

    if (summaryBox) {
        summaryBox.textContent =
            "กำลังวิเคราะห์ภาพรวมอารมณ์ของคลิป...";
    }

    const communicationTableBody =
        document.getElementById(
            "communication-table-body"
        );

    if (communicationTableBody) {
        communicationTableBody.innerHTML = "";

        const loadingRow =
            document.createElement("tr");

        const loadingCell =
            document.createElement("td");

        loadingCell.colSpan = 3;
        loadingCell.style.textAlign = "center";
        loadingCell.style.color = "#64748B";
        loadingCell.textContent =
            "กำลังวิเคราะห์กลยุทธ์การสื่อสาร...";

        loadingRow.appendChild(loadingCell);
        communicationTableBody.appendChild(
            loadingRow
        );
    }
    document.getElementById('recommend-list').innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">กำลังตรวจสอบข้อมูลเชิงสถิติจากเครือข่ายภายนอก...</p>`;
    document.getElementById('chapters-list-container').innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">กำลังจัดสรรสารบัญพิกัดเวลาตามหัวข้อหลัก...</p>`;
    document.getElementById('chapters-list-container').innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">กำลังจัดสรรสารบัญพิกัดเวลาตามหัวข้อหลัก...</p>`;

    const formData = new FormData();
    formData.append('mode', selectedMode);

    const modelSelect = document.getElementById('estimatorModelSelect');
    if (modelSelect) {
        formData.append('model', modelSelect.value);
    }

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
let lastActiveIndex = -1;
let activeRowElement = null;
let isUpdatingSubtitle = false;

// Binary search for finding active timeline item
function findActiveIndex(currentTime) {
    let low = 0;
    let high = globalTimelineData.length - 1;
    while (low <= high) {
        let mid = Math.floor((low + high) / 2);
        let item = globalTimelineData[mid];
        let start = Number(item.start);
        let end = Number(item.end);
        if (isNaN(start) || isNaN(end)) {
            // Fallback กรณีค่าไม่สมบูรณ์
            start = mid * 4;
            end = start + 4;
        }
        if (currentTime >= start && currentTime < end) {
            return mid;
        } else if (currentTime < start) {
            high = mid - 1;
        } else {
            low = mid + 1;
        }
    }
    return -1;
}

function trackLiveSubtitle(currentTime) {
    if (isUpdatingSubtitle) return;
    
    isUpdatingSubtitle = true;
    requestAnimationFrame(() => {
        updateCommunicationMoodByTime(
            currentTime
        );
        document.getElementById('timeMarker').innerText = `📍 พิกัดเวลาตรวจสอบปัจจุบัน: ${formatToExecutiveTime(currentTime)} นาที`;

        const activeIndex = findActiveIndex(currentTime);
        let activeSubText = "🎵 [ ระบบกำลังตรวจสอบความเงียบหรือการประมวลสัญญาณเสียง ]";

        if (activeIndex !== -1) {
            const item = globalTimelineData[activeIndex];
            activeSubText = item.label + " " + item.text;

            if (activeIndex !== lastActiveIndex) {
                // Update active row DOM reference
                if (activeRowElement) {
                    activeRowElement.classList.remove('active-row');
                }
                
                activeRowElement = document.getElementById(`tx-row-${activeIndex}`);
                if (activeRowElement) {
                    activeRowElement.classList.add('active-row');
                    // จำกัด scrollIntoView ให้ทำเฉพาะเมื่อ active index เปลี่ยน
                    activeRowElement.scrollIntoView({ behavior: 'auto', block: 'nearest' });
                }
                lastActiveIndex = activeIndex;
            }
        } else {
            if (activeRowElement) {
                activeRowElement.classList.remove('active-row');
                activeRowElement = null;
            }
            lastActiveIndex = -1;
        }

        document.getElementById('live-sub-box').innerText = activeSubText;
        isUpdatingSubtitle = false;
    });
}



function injectProcessedDataToDashboard(data) {
    const statusBox = document.getElementById('statusBox');
    const rootData = data.result ? data.result : data;
    
    globalTimelineData = rootData.timeline || [];
    originalThaiTextArray = globalTimelineData.map(item => item.text);

    // เก็บค่า รหัสมีเดีย สำหรับการดาวน์โหลดโมดูล 9
    window.activeMediaId = rootData.video_url ? rootData.video_url.split('/').pop().replace('.mp4', '') : null;
    
    // รีเซ็ตสถานะการเลือกดาวน์โหลดเมื่อโหลดวิดีโอใหม่
    currentSelectedDownloadFormat = null;
    document.querySelectorAll('.download-format-card').forEach(card => {
        card.style.borderColor = 'var(--border-color)';
        card.style.boxShadow = 'none';
        card.style.background = 'var(--input-bg)';
    });
    const downloadRadios = document.querySelectorAll('input[name="downloadFormat"]');
    downloadRadios.forEach(radio => radio.checked = false);
    const actionBox = document.getElementById('download-action-box');
    if (actionBox) actionBox.style.display = 'none';

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
        if (document.getElementById('t-topics')) document.getElementById('t-topics').innerText = rootData.telemetry.topics || "-";
    }

    globalKeywordsChartData = rootData.keywords_chart || [];
    if (globalKeywordsChartData.length > 0) drawKeywordBarChart(globalKeywordsChartData);
    renderCommunicationModule(
        rootData.communication_analysis || [],
        rootData.communication_distribution || []
    );
    renderRecommendations(rootData.recommendations || []);
    renderVideoChaptersModule(rootData.video_chapters || []);

    statusBox.style.display = 'none';
    document.getElementById('mainDashboardSelector').value = "transcript";
    executeModuleSwitch();
}

function formatTranscriptTime(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return "--:--";
    return formatToExecutiveTime(seconds);
}

function renderTranscriptComponent(items, keyword = "") {
    const listContainer = document.getElementById('transcript-list');
    listContainer.innerHTML = '';

    if (items.length === 0) {
        listContainer.innerHTML = `<p style="color:#64748B;text-align:center;">ไม่พบชุดข้อความที่ตรงตามเงื่อนไขการค้นหา</p>`;
        return;
    }

    const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const keywordRegex = escapedKeyword ? new RegExp(`(${escapedKeyword})`, "gi") : null;
    let innerHtml = '';

    items.forEach((row, index) => {
        const rowIndex = index;
        let txt = row.text;
        if (keywordRegex) {
            txt = txt.replace(keywordRegex, "<mark>$1</mark>");
        }
        innerHtml += `<div class="transcript-row" id="tx-row-${rowIndex}"><button class="time-badge" onclick="warpToTargetTime(${Number(row.start)})">${formatTranscriptTime(row.start)}</button><div class="phrase-box" onclick="warpToTargetTime(${Number(row.start)})">${txt}</div></div>`;
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
            <td style="vertical-align:top;width:25%; color: var(--primary-color); font-weight: 700;">${row.time_range}</td>
            <td>
                <div style="font-size:15px;color: var(--text-main);margin-bottom:4px; font-weight: 600;">${row.sentiment}</div>
                <div style="font-size:12px;color: var(--text-secondary);margin-bottom:2px;">${row.trigger}</div>
                <div style="font-size:12px;color: var(--primary-color);">${row.purpose}</div>
            </td>`;
        tbody.appendChild(tr);
    });
}

function renderCommunicationModule(
    communicationList,
    emotionSummary
) {
    const tbody = document.getElementById(
        "communication-table-body"
    );

    const summaryContainer =
        document.getElementById(
            "communication-emotion-summary"
        );

    if (!tbody || !summaryContainer) {
        console.error(
            "Module 6 containers not found"
        );
        return;
    }

    tbody.innerHTML = "";
    summaryContainer.textContent =
        typeof emotionSummary === "string"
            ? emotionSummary
            : "ไม่พบข้อมูลภาพรวมอารมณ์";

    globalCommunicationIntervals =
        Array.isArray(communicationList)
            ? communicationList
            : [];

    if (globalCommunicationIntervals.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");

        td.colSpan = 3;
        td.style.textAlign = "center";
        td.style.color = "#64748B";
        td.textContent =
            "ไม่พบข้อมูลกลยุทธ์การสื่อสาร";

        tr.appendChild(td);
        tbody.appendChild(tr);
    } else {
        globalCommunicationIntervals.forEach(
            (row, index) => {
                const tr =
                    document.createElement("tr");

                tr.id =
                    `communication-row-${index}`;

                tr.className =
                    "communication-mood-row";

                const timeCell =
                    document.createElement("td");

                const strategyCell =
                    document.createElement("td");

                const emotionCell =
                    document.createElement("td");

                timeCell.textContent =
                    String(row.time_range || "-");

                strategyCell.textContent =
                    String(row.strategy || "-");

                emotionCell.textContent =
                    String(row.emotion || "เป็นกลาง");

                timeCell.style.color =
                    "var(--primary-color)";

                timeCell.style.fontWeight = "700";
                strategyCell.style.fontWeight = "700";

                tr.appendChild(timeCell);
                tr.appendChild(strategyCell);
                tr.appendChild(emotionCell);
                tbody.appendChild(tr);
            }
        );
    }

    const tableScroll =
        document.querySelector(
            "#module-sentiment "
            + ".communication-table-scroll"
        );

    if (tableScroll) {
        tableScroll.scrollTop = 0;
        tableScroll.scrollLeft = 0;
    }
}

function parseCommunicationTimeToSeconds(value) {
    if (typeof value !== "string") {
        return null;
    }

    const parts = value
        .trim()
        .split(":")
        .map(Number);

    if (
        parts.some(
            (part) => !Number.isFinite(part)
        )
    ) {
        return null;
    }

    if (parts.length === 2) {
        return parts[0] * 60 + parts[1];
    }

    if (parts.length === 3) {
        return (
            parts[0] * 3600
            + parts[1] * 60
            + parts[2]
        );
    }

    return null;
}

function updateCommunicationMoodByTime(currentTime) {
    const playerBox = document.querySelector(".sticky-player-box");
    const badge = document.getElementById("currentMoodBadge");

    if (!playerBox) return;

    // Tone mapping
    const tones = {
        critical: { name: 'Critical', color: '#EF4444', rgb: '239,68,68', icon: '🔴', emotions: ['โกรธ', 'กดดัน', 'ผิดหวัง'] },
        energetic: { name: 'Energetic', color: '#A855F7', rgb: '168,85,247', icon: '🟣', emotions: ['มั่นใจ', 'สร้างแรงบันดาลใจ'] },
        positive: { name: 'Positive', color: '#FFC72C', rgb: '255,199,44', icon: '🟡', emotions: ['เป็นกันเอง', 'สนุกสนาน'] },
        reflective: { name: 'Reflective', color: '#06B6D4', rgb: '6,182,212', icon: '🔵', emotions: ['ชวนคิด', 'สงสัย'] },
        sad: { name: 'Sad', color: '#3B82F6', rgb: '59,130,246', icon: '🔷', emotions: ['เศร้า', 'กังวล', 'เห็นอกเห็นใจ'] },
        neutral: { name: 'Neutral', color: '#22C55E', rgb: '34,197,94', icon: '🟢', emotions: ['เป็นกลาง'] }
    };

    let activeIndex = -1;
    let activeEmotion = "เป็นกลาง";

    for (let index = 0; index < globalCommunicationIntervals.length; index += 1) {
        const item = globalCommunicationIntervals[index];
        const range = String(item.time_range || "").replace("–", "-").replace("—", "-").split("-", 2);
        if (range.length !== 2) continue;
        const start = parseCommunicationTimeToSeconds(range[0]);
        const end = parseCommunicationTimeToSeconds(range[1]);
        if (start === null || end === null) continue;
        if (currentTime >= start && currentTime < end) {
            activeIndex = index;
            activeEmotion = String(item.emotion || "เป็นกลาง");
            break;
        }
    }

    // Find tone based on emotion
    let tone = tones.neutral;
    for (const key in tones) {
        if (tones[key].emotions.includes(activeEmotion)) {
            tone = tones[key];
            break;
        }
    }

    // Handle change
    if (activeIndex !== lastCommunicationIndex) {
        console.debug("Communication mood changed:", {
            currentTime,
            activeIndex,
            emotion: activeEmotion,
            tone: tone.name
        });

        // Update active row
        if (activeCommunicationRow) {
            activeCommunicationRow.classList.remove("communication-mood-row-active");
        }

        if (activeIndex !== -1) {
            playerBox.style.setProperty("--mood-color", tone.color);
            playerBox.style.setProperty("--mood-rgb", tone.rgb);
            playerBox.classList.add("mood-glow-active");

            activeCommunicationRow = document.getElementById(`communication-row-${activeIndex}`);
            if (activeCommunicationRow) {
                activeCommunicationRow.style.setProperty("--mood-color", tone.color);
                activeCommunicationRow.style.setProperty("--mood-rgb", tone.rgb);
                activeCommunicationRow.classList.add("communication-mood-row-active");
            }

            if (badge) {
                badge.style.setProperty("--mood-color", tone.color);
                badge.style.setProperty("--mood-rgb", tone.rgb);
                badge.textContent = `${tone.icon} อารมณ์ปัจจุบัน: ${activeEmotion}`;
            }
        } else {
            playerBox.classList.remove("mood-glow-active");
            if (badge) {
                badge.textContent = "⚪ อารมณ์ปัจจุบัน: ไม่ระบุ";
                badge.style.removeProperty("--mood-color");
                badge.style.removeProperty("--mood-rgb");
            }
        }
        lastCommunicationIndex = activeIndex;
    }
}

// ล้างคอมเมนต์เพื่อความสากล
function drawKeywordBarChart(chartData) {
    const ctx = document.getElementById('keywordBarChart').getContext('2d');
    if (keywordBarChartInstance) keywordBarChartInstance.destroy();
    const limitedData = chartData.slice(0, 5);

    // ตรวจสอบธีมปัจจุบันเพื่อเลือกสีที่แสดงผลลัพธ์คมชัดสูงสุด
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#F5F5F5' : '#111827';
    const subTextColor = isDark ? '#B0B0B0' : '#6B7280';
    const gridColor = isDark ? '#303030' : '#E5E7EB';
    const primaryColor = isDark ? '#3B82F6' : '#2563EB';
    const secondaryColor = isDark ? '#2563EB' : '#3B82F6';

    keywordBarChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: limitedData.map(item => item.keyword),
            datasets: [{ 
                label: 'อัตราความถี่ความหนาแน่นของการตรวจพบคำสำคัญ', 
                data: limitedData.map(item => item.count), 
                backgroundColor: primaryColor, 
                borderColor: secondaryColor, 
                borderWidth: 1 
            }]
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false, 
            scales: { 
                y: { 
                    ticks: { color: subTextColor }, 
                    grid: { color: gridColor } 
                }, 
                x: { 
                    ticks: { color: textColor }, 
                    grid: { display: false } 
                } 
            }, 
            plugins: { 
                legend: { 
                    labels: { 
                        color: textColor, 
                        font: { family: 'Sarabun', weight: 'bold' } 
                    } 
                } 
            } 
        }
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
    
    // 🎯 ถ้า backend ส่ง data มาไม่ตรงคาดการณ์ ให้เช็ก array เปล่าหรือ null
    if (!chapters || chapters.length === 0) {
        container.innerHTML = `<p style="text-align:center;color:#64748B;width:100%;">🔍 ไม่พบหัวข้อหลักหรือหัวข้อย่อยจากผลวิเคราะห์</p>`;
        return;
    }
    
    // ตรวจสอบโครงสร้างข้อมูล ถ้า chapters เป็นโครงสร้างใหม่ ให้ใช้ key ให้ถูกต้อง
    // จาก main.py: video_chapters = [{"start_time_seconds": ..., "chapter_title": ..., "sub_chapters": [...]}, ...]
    
    chapters.forEach(ch => {
        const accordionDetails = document.createElement('details');
        accordionDetails.className = 'chapter-accordion-box';

        const accordionSummary = document.createElement('summary');
        accordionSummary.className = 'chapter-summary-bar';
        
        // ข้อมูลหลัก: start_time_seconds, time_range_label, chapter_title
        const chTitle = ch.chapter_title || "หัวข้อไม่มีชื่อ";
        const chTime = ch.time_range_label || "00:00";
        const chStart = ch.start_time_seconds || 0;
        
        accordionSummary.innerHTML = `
            <div class="summary-left-content">
                <span class="main-chapter-time">⏱️ ${chTime}</span>
                <span class="main-chapter-title">${chTitle}</span>
            </div>
            <span class="toggle-icon-indicator">▼</span>
        `;
        
        accordionSummary.addEventListener('click', (e) => {
            warpToTargetTime(chStart);
        });

        accordionDetails.appendChild(accordionSummary);

        // หัวข้อย่อย: sub_chapters: [{sub_title, start_time_seconds, time_range_label}, ...]
        if (ch.sub_chapters && ch.sub_chapters.length > 0) {
            const subChaptersWrapper = document.createElement('div');
            subChaptersWrapper.className = 'sub-chapters-dropdown-container';

            ch.sub_chapters.forEach(sub => {
                const subItemCard = document.createElement('div');
                subItemCard.className = 'sub-chapter-node-item';
                
                const subTitle = sub.sub_title || "หัวข้อย่อยไม่มีชื่อ";
                const subTime = sub.time_range_label || "00:00";
                const subStart = sub.start_time_seconds || 0;
                
                subItemCard.innerHTML = `
                    <span class="sub-node-time">📌 ${subTime}</span>
                    <span class="sub-node-text">${subTitle}</span>
                `;
                
                subItemCard.onclick = (e) => {
                    e.stopPropagation(); 
                    warpToTargetTime(subStart);
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

// --- 🖱️ ระบบ Spotlight Hover Effect จับพิกัดเมาส์เรืองแสงสไตล์ Sci-Fi ---
function initSpotlight() {
    document.addEventListener('mousemove', (e) => {
        const card = e.target.closest('.dashboard-box');
        if (!card) return;
        
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left; // พิกัด X สัมพัทธ์กับการ์ด
        const y = e.clientY - rect.top;  // พิกัด Y สัมพัทธ์กับการ์ด
        
        card.style.setProperty('--mouse-x', `${x}px`);
        card.style.setProperty('--mouse-y', `${y}px`);
    });
}

// โหลด Spotlight ทันทีพร้อม DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSpotlight);
} else {
    initSpotlight();
}

// --- 📥 โมดูลที่ 9: ระบบควบคุมและดาวน์โหลดคำบรรยาย (Module 9 Engine) ---
let currentSelectedDownloadFormat = null;

function handleDownloadFormatChange(format) {
    currentSelectedDownloadFormat = format;
    
    // รีเซ็ตการไฮไลท์ทุกการ์ด
    document.querySelectorAll('.download-format-card').forEach(card => {
        card.style.borderColor = 'var(--border-color)';
        card.style.boxShadow = 'none';
        card.style.background = 'var(--input-bg)';
    });
    
    // ไฮไลท์การ์ดที่ถูกเลือก
    const selectedId = 'card-format-' + format;
    const selectedCard = document.getElementById(selectedId);
    if (selectedCard) {
        selectedCard.style.borderColor = 'var(--primary-color)';
        selectedCard.style.boxShadow = '0 0 15px rgba(37, 99, 235, 0.2)';
        selectedCard.style.background = 'var(--box-inner-bg)';
    }
    
    // แสดงกล่องปุ่มดาวน์โหลดอย่างนุ่มนวล
    const actionBox = document.getElementById('download-action-box');
    if (actionBox) {
        actionBox.style.display = 'block';
    }
}

function executeDownloadAction() {
    if (!window.activeMediaId) {
        alert('❌ กรุณาทำการประมวลผลหรือโหลดข้อมูลสื่อก่อนทำรายการดาวน์โหลดครับ');
        return;
    }
    if (!currentSelectedDownloadFormat) {
        alert('❌ กรุณาเลือกรูปแบบไฟล์ (.txt หรือ .pdf) ก่อนครับ');
        return;
    }
    
    // ทริกเกอร์เรียกเปิดลิงก์ดาวน์โหลดหน้าต่างใหม่
    const downloadUrl = `/download/${currentSelectedDownloadFormat}/${window.activeMediaId}`;
    window.open(downloadUrl, '_blank');
}
