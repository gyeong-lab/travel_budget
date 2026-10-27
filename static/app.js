// static/app.js - Vanilla JavaScript with strict Console Logging & Chart.js
let currentDiagnosis = null;
let currentRunResult = null;
let currentChart = null;

document.addEventListener('DOMContentLoaded', () => {
    console.log('[PAGE] 페이지 로드 완료');
    checkServerHealth();
    initUploadEvents();
});

// 1. 서버 헬스체크
async function checkServerHealth() {
    try {
        const res = await fetch('/health');
        const data = await res.json();
        const badge = document.getElementById('server-status-badge');
        if (data.status === 'ok') {
            const keyText = data.has_api_key ? 'Gemini 연동 활성' : '로컬 모드 (키 미설정)';
            badge.innerHTML = `<span class="status-dot online"></span> ${data.model} (${keyText})`;
        }
    } catch (err) {
        console.error('[ERROR] 서버 상태 확인 실패:', err);
    }
}

// 2. 업로드 이벤트 설정
function initUploadEvents() {
    const dropArea = document.getElementById('drop-area');
    const fileInput = document.getElementById('file-input');

    dropArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropArea.style.borderColor = '#1d4ed8';
        dropArea.style.background = '#e0f2fe';
    });

    dropArea.addEventListener('dragleave', () => {
        dropArea.style.borderColor = '#93c5fd';
        dropArea.style.background = '#eff6ff';
    });

    dropArea.addEventListener('drop', (e) => {
        e.preventDefault();
        dropArea.style.borderColor = '#93c5fd';
        dropArea.style.background = '#eff6ff';
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });
}

// 3. 파일 선택 및 /inspect 진단 요청
async function handleFileSelect(file) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
        alert('CSV 파일만 업로드할 수 있습니다.');
        console.error('[ERROR] CSV 파일이 아닌 파일 업로드 시도:', file.name);
        return;
    }

    console.log(`[UPLOAD] 파일 선택: name=${file.name}, size=${file.size} bytes`);

    const loading = document.getElementById('upload-loading');
    const panel = document.getElementById('diagnosis-panel');
    loading.classList.remove('hidden');
    panel.classList.add('hidden');

    const formData = new FormData();
    formData.append('file', file);

    console.log('[INSPECT] 진단 요청 시작');
    try {
        const res = await fetch('/inspect', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        loading.classList.add('hidden');

        if (data.success) {
            currentDiagnosis = data.diagnosis;
            console.log(`[INSPECT] 진단 응답 수신: rows=${currentDiagnosis.rows}, cols=${currentDiagnosis.columns}, warnings=${currentDiagnosis.warnings.length}`);
            renderDiagnosis(currentDiagnosis);
            setStepperActive(1);
        } else {
            console.error('[ERROR] 진단 실패:', data.error);
            alert(`진단 오류: ${data.error}`);
        }
    } catch (err) {
        loading.classList.add('hidden');
        console.error('[ERROR] /inspect 통신 실패:', err);
        alert(`서버 통신 오류: ${err.message}`);
    }
}

// 4. 진단 결과 렌더링
function renderDiagnosis(d) {
    document.getElementById('diag-filename').innerText = d.filename;
    document.getElementById('diag-filesize').innerText = formatBytes(d.file_size);
    document.getElementById('diag-encoding').innerText = d.encoding;
    document.getElementById('diag-skipped').innerText = d.skipped_lines;
    document.getElementById('diag-shape').innerText = `${d.rows}행 × ${d.columns}열`;

    // 경고
    const warnBox = document.getElementById('diag-warnings');
    if (d.warnings && d.warnings.length > 0) {
        warnBox.innerHTML = '<strong>⚠️ 데이터 주의사항:</strong><br>' + d.warnings.map(w => `• ${w}`).join('<br>');
        warnBox.classList.remove('hidden');
    } else {
        warnBox.classList.add('hidden');
    }

    // 열 역할 후보
    const roles = d.role_candidates;
    document.getElementById('role-place').innerText = roles.place.length > 0 ? roles.place.join(', ') : '(미감지)';
    document.getElementById('role-cost').innerText = roles.cost.length > 0 ? roles.cost.join(', ') : '(미감지)';
    document.getElementById('role-sat').innerText = roles.satisfaction.length > 0 ? roles.satisfaction.join(', ') : '(미감지)';
    document.getElementById('role-period').innerText = roles.period.length > 0 ? roles.period.join(', ') : '(단일시점)';
    document.getElementById('rec-period-tag').innerText = `권장 기준시점: ${d.recommended_period}`;

    // 테이블 미리보기
    const thead = document.getElementById('preview-thead');
    const tbody = document.getElementById('preview-tbody');
    thead.innerHTML = `<tr>${d.column_names.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>`;
    tbody.innerHTML = d.preview.map(row => {
        return `<tr>${d.column_names.map(c => `<td>${escapeHtml(String(row[c] !== null && row[c] !== undefined ? row[c] : ''))}</td>`).join('')}</tr>`;
    }).join('');

    document.getElementById('diagnosis-panel').classList.remove('hidden');
}

// 5. 2단계: AI 통계 분석 제안 요청 (/suggest)
async function requestSuggestions() {
    console.log('[SUGGEST] 제안 요청 시작');
    const suggestSec = document.getElementById('section-suggest');
    const loading = document.getElementById('suggest-loading');
    const list = document.getElementById('suggestions-list');

    suggestSec.classList.remove('hidden');
    loading.classList.remove('hidden');
    list.innerHTML = '';
    suggestSec.scrollIntoView({ behavior: 'smooth' });
    setStepperActive(2);

    try {
        const res = await fetch('/suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        loading.classList.add('hidden');

        if (data.success && data.suggestions) {
            console.log(`[SUGGEST] 제안 응답 수신: ${data.suggestions.length}개 제안 수신 (출처: ${data.source})`);
            renderSuggestions(data.suggestions);
        } else {
            console.error('[ERROR] 제안 수신 실패:', data.error);
            alert(`제안 오류: ${data.error}`);
        }
    } catch (err) {
        loading.classList.add('hidden');
        console.error('[ERROR] /suggest 통신 실패:', err);
        alert(`제안 요청 중 네트워크 오류가 발생했습니다: ${err.message}`);
    }
}

function renderSuggestions(sugs) {
    const list = document.getElementById('suggestions-list');
    list.innerHTML = sugs.map((s, idx) => {
        const paramsStr = JSON.stringify(s.params);
        return `
            <div class="suggestion-card">
                <div class="sug-header">
                    <span class="sug-tool-badge">도구: ${escapeHtml(s.tool)}</span>
                    <span class="highlight-tag">기준시점: ${escapeHtml(s.reference_period || 'ALL')}</span>
                </div>
                <p class="sug-why"><strong>💡 제안 이유:</strong> ${escapeHtml(s.why)}</p>
                <div class="sug-caution"><strong>⚠️ 주의사항:</strong> ${escapeHtml(s.caution)}</div>
                <button class="btn btn-primary" onclick='executeTool("${escapeHtml(s.tool)}", ${paramsStr})'>
                    이 도구로 분석 실행하기 →
                </button>
            </div>
        `;
    }).join('');
}

// 6. 3단계: 도구 실행 (/run)
async function executeTool(toolName, params) {
    console.log(`[RUN] 도구 실행 시작: tool=${toolName}, ref=${params.reference_period || 'ALL'}`);
    const runSec = document.getElementById('section-run');
    runSec.classList.remove('hidden');
    runSec.scrollIntoView({ behavior: 'smooth' });
    setStepperActive(3);

    try {
        const res = await fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool: toolName, params: params })
        });
        const data = await res.json();

        if (data.success) {
            currentRunResult = data.data;
            console.log('[RUN] 도구 실행 결과 수신 성공');
            renderRunResult(currentRunResult);
        } else {
            console.error('[ERROR] 도구 실행 실패:', data.error);
            alert(`계산 오류: ${data.error}`);
        }
    } catch (err) {
        console.error('[ERROR] /run 통신 오류:', err);
        alert(`도구 실행 통신 오류: ${err.message}`);
    }
}

function renderRunResult(data) {
    document.getElementById('run-tool-name').innerText = data.tool;
    document.getElementById('run-ref-period').innerText = data.reference_period || 'ALL';
    document.getElementById('run-rows-used').innerText = `${data.rows_used}행`;
    document.getElementById('run-rows-excluded').innerText = `${data.rows_excluded}행`;

    const exBox = document.getElementById('run-exclusion-box');
    if (data.exclusion_reasons && data.exclusion_reasons.length > 0) {
        exBox.innerHTML = `<strong>제외 사유:</strong> ${data.exclusion_reasons.join(', ')}`;
    } else {
        exBox.innerHTML = `<strong>제외 사유:</strong> 결측치 없이 모든 행을 정상 분석했습니다.`;
    }

    // JSON 상세 덤프
    document.getElementById('run-result-dump').innerText = JSON.stringify(data.result, null, 2);

    // 차트 렌더링
    renderChart(data);
}

// 7. Chart.js 렌더링
function renderChart(data) {
    const ctx = document.getElementById('analysisChart').getContext('2d');
    if (currentChart) {
        currentChart.destroy();
    }

    const chartInfo = data.chart;
    if (!chartInfo) {
        console.log('[CHART] 별도 시각화 차트가 없는 도구입니다.');
        return;
    }

    console.log(`[CHART] 차트 렌더 완료: type=${chartInfo.type}`);

    if (chartInfo.type === 'scatter') {
        // 산점도 + 회귀선
        const scatterPoints = chartInfo.points.map(p => ({ x: p.x, y: p.y, label: p.label }));
        const trendline = chartInfo.trendline;

        currentChart = new Chart(ctx, {
            data: {
                datasets: [
                    {
                        type: 'scatter',
                        label: '여행지 관측점',
                        data: scatterPoints,
                        backgroundColor: '#3b82f6',
                        pointRadius: 6
                    },
                    {
                        type: 'line',
                        label: `OLS 회귀선 (${data.result.regression_formula || ''})`,
                        data: trendline,
                        borderColor: '#ef4444',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                if (ctx.dataset.type === 'scatter') {
                                    return `${ctx.raw.label}: (X: ${ctx.raw.x}, Y: ${ctx.raw.y})`;
                                }
                                return ctx.dataset.label;
                            }
                        }
                    }
                }
            }
        });
    } else if (chartInfo.type === 'horizontal_bar') {
        currentChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartInfo.top_labels,
                datasets: [{
                    label: data.unit || '수치',
                    data: chartInfo.top_values,
                    backgroundColor: '#10b981',
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false
            }
        });
    } else if (chartInfo.type === 'bar') {
        currentChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartInfo.labels,
                datasets: [{
                    label: data.unit || '수치',
                    data: chartInfo.values,
                    backgroundColor: '#3b82f6',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    } else if (chartInfo.type === 'line') {
        currentChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartInfo.x_axis,
                datasets: chartInfo.datasets.map(s => ({
                    label: s.label,
                    data: s.values,
                    borderColor: getRandomColor(),
                    fill: false
                }))
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }
}

// 8. 4단계: AI 해석 (/explain)
function goToExplainStep() {
    const expSec = document.getElementById('section-explain');
    expSec.classList.remove('hidden');
    expSec.scrollIntoView({ behavior: 'smooth' });
    setStepperActive(4);
}

function changeExplainMode() {
    const mode = document.querySelector('input[name="explain-mode"]:checked').value;
    console.log(`[EXPLAIN] 모드 변경: ${mode}`);
}

async function requestExplain() {
    const mode = document.querySelector('input[name="explain-mode"]:checked').value;
    console.log(`[EXPLAIN] 해석 요청 시작: mode=${mode}`);

    const loading = document.getElementById('explain-loading');
    const panel = document.getElementById('explain-result-panel');
    const content = document.getElementById('explain-text-content');

    loading.classList.remove('hidden');
    panel.classList.add('hidden');

    try {
        const res = await fetch('/explain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        const data = await res.json();
        loading.classList.add('hidden');

        if (data.success) {
            console.log(`[EXPLAIN] 해석 응답 수신 성공: mode=${data.mode}`);
            content.innerHTML = formatMarkdown(data.explanation);
            panel.classList.remove('hidden');
        } else {
            console.error('[ERROR] 해석 실패:', data.error);
            alert(`해석 오류: ${data.error}`);
        }
    } catch (err) {
        loading.classList.add('hidden');
        console.error('[ERROR] /explain 통신 오류:', err);
        alert(`해석 요청 중 오류가 발생했습니다: ${err.message}`);
    }
}

// 9. 유틸리티 함수
function setStepperActive(stepNum) {
    for (let i = 1; i <= 4; i++) {
        const item = document.getElementById(`step-nav-${i}`);
        if (i <= stepNum) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    }
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/## (.*)/g, '<h2>$1</h2>')
        .replace(/# (.*)/g, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\n- (.*)/g, '<li>$1</li>')
        .replace(/\n\n/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

function getRandomColor() {
    const letters = '0123456789ABCDEF';
    let color = '#';
    for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
    }
    return color;
}
