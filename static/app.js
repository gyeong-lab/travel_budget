// static/app.js - 한국 관광지 관련 데이터 분석 (Korea Tourism Insight)

const SHORT_REGIONS = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'];

const FULL_NAME_MAP = {
    '서울': '서울특별시',
    '부산': '부산광역시',
    '대구': '대구광역시',
    '인천': '인천광역시',
    '광주': '광주광역시',
    '대전': '대전광역시',
    '울산': '울산광역시',
    '세종': '세종특별자치시',
    '경기': '경기도',
    '강원': '강원특별자치도',
    '충북': '충청북도',
    '충남': '충청남도',
    '전북': '전북특별자치도',
    '전남': '전라남도',
    '경북': '경상북도',
    '경남': '경상남도',
    '제주': '제주특별자치도'
};

const REVERSE_NAME_MAP = {};
Object.entries(FULL_NAME_MAP).forEach(([k, v]) => {
    REVERSE_NAME_MAP[v] = k;
    REVERSE_NAME_MAP[k] = k;
});

// 17개 광역시도 공식 실측 데이터 정합 테이블 (단위: 지출액 천원, 만족도 100점)
const REGION_DATA = {
    '제주': { exp: 135.0, sat: 83.2, reb: 78.4, cost: 71.6, daySat: 81.5, staySat: 83.9, quad: 'Q1_high_high' },
    '강원': { exp: 126.0, sat: 81.0, reb: 76.2, cost: 70.8, daySat: 79.2, staySat: 81.8, quad: 'Q1_high_high' },
    '경기': { exp: 102.0, sat: 79.1, reb: 74.5, cost: 68.5, daySat: 78.0, staySat: 79.8, quad: 'Q4_high_low' },
    '전남': { exp: 72.0,  sat: 81.1, reb: 75.8, cost: 73.1, daySat: 79.5, staySat: 81.9, quad: 'Q1_high_high' },
    '경남': { exp: 70.0,  sat: 82.3, reb: 77.0, cost: 72.5, daySat: 80.1, staySat: 82.9, quad: 'Q1_high_high' },
    '경북': { exp: 70.0,  sat: 80.0, reb: 74.2, cost: 71.0, daySat: 78.5, staySat: 80.6, quad: 'Q4_high_low' },
    '충남': { exp: 58.0,  sat: 80.3, reb: 74.8, cost: 72.0, daySat: 79.0, staySat: 81.0, quad: 'Q1_high_high' },
    '부산': { exp: 51.0,  sat: 82.0, reb: 77.5, cost: 71.8, daySat: 80.5, staySat: 82.5, quad: 'Q1_high_high' },
    '전북': { exp: 44.0,  sat: 80.5, reb: 75.0, cost: 74.2, daySat: 79.8, staySat: 81.2, quad: 'Q2_low_high' },
    '서울': { exp: 32.0,  sat: 79.1, reb: 73.8, cost: 67.9, daySat: 78.2, staySat: 79.9, quad: 'Q3_low_low' },
    '충북': { exp: 31.0,  sat: 79.6, reb: 73.5, cost: 72.8, daySat: 78.8, staySat: 80.2, quad: 'Q3_low_low' },
    '인천': { exp: 20.0,  sat: 78.4, reb: 72.1, cost: 69.5, daySat: 77.5, staySat: 79.0, quad: 'Q3_low_low' },
    '대구': { exp: 13.0,  sat: 79.0, reb: 72.9, cost: 71.2, daySat: 78.1, staySat: 79.5, quad: 'Q3_low_low' },
    '대전': { exp: 12.0,  sat: 77.7, reb: 71.5, cost: 70.5, daySat: 76.9, staySat: 78.3, quad: 'Q3_low_low' },
    '울산': { exp: 8.0,   sat: 79.9, reb: 73.0, cost: 71.9, daySat: 78.7, staySat: 80.4, quad: 'Q3_low_low' },
    '광주': { exp: 6.0,   sat: 81.0, reb: 75.2, cost: 74.5, daySat: 80.0, staySat: 81.7, quad: 'Q2_low_high' },
    '세종': { exp: 3.0,   sat: 78.2, reb: 71.8, cost: 70.1, daySat: 77.2, staySat: 78.9, quad: 'Q3_low_low' }
};

let currentRegion = '제주';
let datasets = [];

// 차트 객체 참조
let consumptionDonutChart = null;
let tripTypeBarChart = null;
let regionalBenchmarkBarChart = null;
let comboTrendChart = null;
let quadrantMatrixChart = null;
let agePyramidChart = null;

// 금액을 '원' 단위 콤마 포맷으로 변환 (천원 -> 원)
function formatWon(valInThousands) {
    if (valInThousands === null || valInThousands === undefined || isNaN(valInThousands)) return '-';
    const won = Math.round(valInThousands * 1000);
    return won.toLocaleString('ko-KR') + '원';
}

function getFullName(shortOrFull) {
    return FULL_NAME_MAP[shortOrFull] || shortOrFull;
}

function getShortName(shortOrFull) {
    return REVERSE_NAME_MAP[shortOrFull] || shortOrFull;
}

document.addEventListener('DOMContentLoaded', () => {
    initRegionChips();
    selectRegion('제주');
    loadRegionalBenchmark();
    renderTreemap();
    renderComboChart();
    renderTop5Widgets();
    renderQuadrantMatrix();
    selectAgeTab('전체');
    initDatasets();
});

// 1. 17개 광역시도 풀네임 칩 생성 및 선택
function initRegionChips() {
    const bar = document.getElementById('region-chips-bar');
    if (!bar) return;
    bar.innerHTML = SHORT_REGIONS.map(reg => {
        const full = FULL_NAME_MAP[reg];
        return `
            <button onclick="selectRegion('${reg}')" id="chip-reg-${reg}" class="region-chip ${reg === currentRegion ? 'active' : ''}">
                ${full}
            </button>
        `;
    }).join('');
}

function onGlobalRegionChange(val) {
    if (val === '전국') {
        switchTab('tab-treemap');
    } else {
        const shortName = getShortName(val);
        selectRegion(shortName);
        switchTab('tab-summary');
    }
}

async function selectRegion(regionName) {
    const shortName = getShortName(regionName);
    currentRegion = shortName;
    const fullName = getFullName(shortName);

    // 1. 17개 칩 버튼 활성화 상태 동기화
    SHORT_REGIONS.forEach(reg => {
        const chip = document.getElementById(`chip-reg-${reg}`);
        if (chip) {
            if (reg === shortName) chip.classList.add('active');
            else chip.classList.remove('active');
        }
    });

    // 2. 상단 글로벌 셀렉트 동기화
    const globalSelect = document.getElementById('global-region-select');
    if (globalSelect) {
        globalSelect.value = fullName;
    }

    // 3. 하단 섹션 및 차트의 지역 라벨들 즉시 동기화
    const benchName = document.getElementById('benchmark-selected-name');
    if (benchName) benchName.innerText = fullName;

    const donutTitle = document.getElementById('donut-region-title');
    if (donutTitle) donutTitle.innerText = fullName;

    const donutSub = document.getElementById('donut-region-sub');
    if (donutSub) donutSub.innerText = fullName;

    const tripTitle = document.getElementById('triptype-region-title');
    if (tripTitle) tripTitle.innerText = fullName;

    const tripSub = document.getElementById('triptype-region-sub');
    if (tripSub) tripSub.innerText = fullName;

    // 4. 로컬 실측 데이터로 0ms 즉시 화면 렌더링 (지연 없이 즉각 반응)
    const local = REGION_DATA[shortName];
    if (local) {
        const titleElem = document.getElementById('kpi-region-title');
        if (titleElem) titleElem.innerText = fullName;
        
        let quadText = "알뜰실속형";
        if (local.exp >= 53.9 && local.sat >= 80.3) quadText = "고비용·고만족 (프리미엄 체험지)";
        else if (local.exp < 53.9 && local.sat >= 80.3) quadText = "저비용·고만족 (최고 가성비 추천지)";
        else if (local.exp < 53.9 && local.sat < 80.3) quadText = "저비용·저만족 (경제적 체류지)";
        else quadText = "고비용·저만족 (비효율 주의 지역)";
        const badgeElem = document.getElementById('kpi-quadrant-badge');
        if (badgeElem) badgeElem.innerText = quadText;

        const expElem = document.getElementById('kpi-exp-val');
        if (expElem) expElem.innerText = formatWon(local.exp);
        const expDiff = local.exp - 53.9;
        const expSubElem = document.getElementById('kpi-exp-sub');
        if (expSubElem) {
            expSubElem.innerHTML = `
                <span class="text-[#0284c7] font-bold">1회 여행 지출</span>
                <span class="${expDiff >= 0 ? 'text-blue-600' : 'text-slate-500'} font-bold">
                    ${expDiff >= 0 ? `+${formatWon(expDiff)}` : `-${formatWon(Math.abs(expDiff))}`}
                </span>
            `;
        }

        const satElem = document.getElementById('kpi-sat-val');
        if (satElem) satElem.innerText = `${local.sat}점`;
        const satDiff = (local.sat - 80.3).toFixed(1);
        const satSubElem = document.getElementById('kpi-sat-sub');
        if (satSubElem) {
            satSubElem.innerHTML = `
                <span class="text-emerald-700 font-bold">전반적 만족도</span>
                <span class="${satDiff >= 0 ? 'text-emerald-600' : 'text-slate-500'} font-bold">
                    ${satDiff >= 0 ? `+${satDiff}점` : `${satDiff}점`}
                </span>
            `;
        }

        const rebElem = document.getElementById('kpi-reb-val');
        if (rebElem) rebElem.innerText = `${local.reb}점`;
        const rebSubElem = document.getElementById('kpi-reb-sub');
        if (rebSubElem) {
            rebSubElem.innerHTML = `
                <span class="text-purple-700 font-bold">재방문 의향</span>
                <span class="text-purple-600 font-bold">${local.reb >= 76.0 ? '상위권' : '보통'}</span>
            `;
        }

        const costElem = document.getElementById('kpi-cost-val');
        if (costElem) costElem.innerText = `${local.cost}점`;
        const costSubElem = document.getElementById('kpi-cost-sub');
        if (costSubElem) {
            costSubElem.innerHTML = `
                <span class="text-amber-700 font-bold">체감 물가</span>
                <span class="${local.cost >= 72.0 ? 'text-emerald-600' : 'text-rose-500'} font-bold">
                    ${local.cost >= 72.0 ? '물가 만족' : '물가 불만 상존'}
                </span>
            `;
        }

        renderTripTypeBarChart(local.daySat, local.staySat, fullName);
    }

    // 5. 하단 17개 광역시도 벤치마크 바 차트 & 랭킹 테이블 강조 동기화 (선택 지역 빨간색 하이라이트)
    loadRegionalBenchmark();

    // 6. 서버 API 데이터 비동기 연동 (선택 지역과 일치할 때만 갱신)
    try {
        const res = await fetch(`/api/region-summary/${encodeURIComponent(shortName)}?region=${encodeURIComponent(shortName)}`);
        const data = await res.json();
        if (data.success && (data.region === shortName || getShortName(data.region) === shortName) && currentRegion === shortName) {
            renderRegionKPIs(data);
            renderConsumptionDonutChart(data.consumption_shares);
            renderTripTypeBarChart(data.metrics.day_trip, data.metrics.stay_trip, fullName);
        }
    } catch (e) {
        console.error('지역 브리핑 로드 오류:', e);
    }
}

function renderRegionKPIs(data) {
    if (!data || !data.region) return;
    const short = getShortName(data.region);
    // 엄격 가드: 사용자가 선택한 현재 지역과 일치하지 않는 서버 응답은 절대 DOM을 덮어쓰지 않음
    if (short !== currentRegion) return;

    const m = data.metrics;
    const fullName = getFullName(data.region);
    document.getElementById('kpi-region-title').innerText = fullName;
    document.getElementById('kpi-quadrant-badge').innerText = data.quadrant;

    // 1. 지출액 (원 단위)
    const exp = m.expense;
    document.getElementById('kpi-exp-val').innerText = exp.val !== null ? formatWon(exp.val) : '-';
    document.getElementById('kpi-exp-sub').innerHTML = `
        <span class="text-[#0284c7] font-bold">전국 ${exp.rank || '-'}위</span>
        <span class="${exp.diff >= 0 ? 'text-blue-600' : 'text-slate-500'} font-bold">
            ${exp.diff !== null ? (exp.diff >= 0 ? `+${formatWon(exp.diff)}` : `-${formatWon(Math.abs(exp.diff))}`) : '-'}
        </span>
    `;

    // 2. 만족도
    const sat = m.satisfaction;
    document.getElementById('kpi-sat-val').innerText = sat.val !== null ? `${sat.val}점` : '-';
    document.getElementById('kpi-sat-sub').innerHTML = `
        <span class="text-emerald-700 font-bold">전국 ${sat.rank || '-'}위</span>
        <span class="${sat.diff >= 0 ? 'text-emerald-600' : 'text-slate-500'} font-bold">
            ${sat.diff !== null ? (sat.diff >= 0 ? `+${sat.diff}점` : `${sat.diff}점`) : '-'}
        </span>
    `;

    // 3. 재방문 의향
    const reb = m.revisit;
    document.getElementById('kpi-reb-val').innerText = reb.val !== null ? `${reb.val}점` : '-';
    document.getElementById('kpi-reb-sub').innerHTML = `
        <span class="text-purple-700 font-bold">전국 ${reb.rank || '-'}위</span>
        <span class="text-purple-600 font-bold">재방문 평가 지수</span>
    `;

    // 4. 물가 만족도
    const cost = m.cost_satisfaction;
    document.getElementById('kpi-cost-val').innerText = cost.val !== null ? `${cost.val}점` : '-';
    document.getElementById('kpi-cost-sub').innerHTML = `
        <span class="text-amber-700 font-bold">전국 ${cost.rank || '-'}위</span>
        <span class="${cost.diff >= 0 ? 'text-emerald-600' : 'text-rose-500'} font-bold">
            ${cost.diff !== null ? (cost.diff >= 0 ? `+${cost.diff}점` : `${cost.diff}점`) : '-'}
        </span>
    `;
}

// 2. 업종별 소비 비중 도넛 차트
function renderConsumptionDonutChart(shares) {
    const canvas = document.getElementById('consumptionDonutChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (consumptionDonutChart) consumptionDonutChart.destroy();

    const labels = Object.keys(shares);
    const dataVals = Object.values(shares);

    consumptionDonutChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataVals,
                backgroundColor: [
                    '#00a3e0', // 외식비
                    '#1e293b', // 교통비
                    '#6366f1', // 숙박비
                    '#10b981', // 카페/식음료
                    '#f59e0b', // 여가활동
                    '#ec4899', // 쇼핑비
                    '#94a3b8'  // 기타
                ],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { boxWidth: 12, font: { size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.label}: ${ctx.parsed}%`
                    }
                }
            },
            cutout: '65%'
        }
    });
}

// 3. 당일 vs 숙박 만족도 바 차트
function renderTripTypeBarChart(dayTrip, stayTrip, fullName) {
    const canvas = document.getElementById('tripTypeBarChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (tripTypeBarChart) tripTypeBarChart.destroy();

    const dayVal = typeof dayTrip === 'number' ? dayTrip : ((dayTrip && dayTrip.val) || 0);
    const dayAvg = (dayTrip && dayTrip.avg) || 79.4;
    const stayVal = typeof stayTrip === 'number' ? stayTrip : ((stayTrip && stayTrip.val) || 0);
    const stayAvg = (stayTrip && stayTrip.avg) || 81.1;

    tripTypeBarChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['당일여행 만족도', '숙박여행 만족도'],
            datasets: [
                {
                    label: `${fullName} 실측치`,
                    data: [dayVal, stayVal],
                    backgroundColor: '#00a3e0',
                    borderRadius: 6
                },
                {
                    label: '전국 평균치',
                    data: [dayAvg, stayAvg],
                    backgroundColor: '#cbd5e1',
                    borderRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { boxWidth: 12, font: { size: 11 } }
                }
            },
            scales: {
                y: { min: 70, max: 90, grid: { color: '#f1f5f9' } },
                x: { grid: { display: false } }
            }
        }
    });
}

// 4. 17개 광역시도 벤치마크 랭킹 & 비교 바 차트 (순위 클릭 시 자동 전환 연동)
function loadRegionalBenchmark() {
    const metric = document.getElementById('compare-metric-select').value;
    const canvas = document.getElementById('regionalBenchmarkBarChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (regionalBenchmarkBarChart) regionalBenchmarkBarChart.destroy();

    // 지표별 데이터 추출 및 정렬
    const items = Object.entries(REGION_DATA).map(([reg, d]) => {
        let val = 0;
        let formattedVal = '';
        if (metric === 'exp') {
            val = d.exp;
            formattedVal = formatWon(d.exp);
        } else if (metric === 'sat') {
            val = d.sat;
            formattedVal = `${d.sat}점`;
        } else if (metric === 'reb') {
            val = d.reb;
            formattedVal = `${d.reb}점`;
        } else if (metric === 'cost') {
            val = d.cost;
            formattedVal = `${d.cost}점`;
        } else if (metric === 'vfm') {
            val = parseFloat((d.sat / d.exp).toFixed(2));
            formattedVal = `${val} (효율)`;
        }
        return {
            short: reg,
            full: FULL_NAME_MAP[reg],
            value: val,
            formatted: formattedVal
        };
    });

    items.sort((a, b) => b.value - a.value);

    // 평균 계산
    const sum = items.reduce((acc, cur) => acc + cur.value, 0);
    const avg = sum / items.length;

    // 선택된 지역만 강렬한 빨간색(#ef4444), 나머지 16개 지역은 은은한 중립 슬레이트(#94a3b8)
    const barBgColors = items.map(i => i.short === currentRegion ? '#ef4444' : '#94a3b8');
    const barBorderColors = items.map(i => i.short === currentRegion ? '#b91c1c' : '#64748b');
    const borderWidths = items.map(i => i.short === currentRegion ? 2.5 : 1);

    // 차트 생성
    regionalBenchmarkBarChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: items.map(i => i.full),
            datasets: [{
                label: document.getElementById('compare-metric-select').selectedOptions[0].text,
                data: items.map(i => i.value),
                backgroundColor: barBgColors,
                borderColor: barBorderColors,
                borderWidth: borderWidths,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const idx = ctx.dataIndex;
                            return ` ${items[idx].full}: ${items[idx].formatted}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { font: { size: 10, weight: 'bold' } },
                    grid: { display: false }
                },
                y: {
                    grid: { color: '#f1f5f9' },
                    ticks: {
                        callback: (v) => metric === 'exp' ? `${Math.round(v * 1000).toLocaleString()}원` : v
                    }
                }
            }
        }
    });

    // 랭킹 테이블 렌더링 (클릭 시 자동 전환)
    const tbody = document.getElementById('benchmark-ranking-tbody');
    if (!tbody) return;

    tbody.innerHTML = items.map((item, idx) => {
        const isCurrent = item.short === currentRegion;
        const diff = item.value - avg;
        let diffText = '';
        if (metric === 'exp') {
            diffText = diff >= 0 ? `+${formatWon(diff)}` : `-${formatWon(Math.abs(diff))}`;
        } else {
            diffText = diff >= 0 ? `+${diff.toFixed(2)}` : diff.toFixed(2);
        }

        return `
            <tr onclick="onBenchmarkRowClick('${item.short}')" class="transition cursor-pointer ${isCurrent ? 'bg-rose-50/90 border-l-4 border-l-rose-500 font-extrabold shadow-2xs' : 'hover:bg-slate-50'}">
                <td class="p-3 font-mono font-bold text-slate-800">
                    <span class="inline-flex items-center justify-center w-6 h-6 rounded-md ${isCurrent ? 'bg-rose-500 text-white font-black' : (idx < 3 ? 'bg-amber-100 text-amber-900 font-black' : 'bg-slate-100 text-slate-600')} text-xs">
                        ${idx + 1}
                    </span>
                </td>
                <td class="p-3 font-bold text-[#0b1b3d] flex items-center gap-2">
                    <span class="${isCurrent ? 'text-rose-700 text-sm font-black' : ''}">${item.full}</span>
                    ${isCurrent ? '<span class="text-[10px] bg-rose-500 text-white px-2 py-0.5 rounded-full font-black animate-pulse">선택 지역</span>' : ''}
                </td>
                <td class="p-3 font-extrabold ${isCurrent ? 'text-rose-600 text-sm' : 'text-slate-700'}">${item.formatted}</td>
                <td class="p-3 font-semibold ${diff >= 0 ? 'text-emerald-600' : 'text-slate-500'}">${diffText}</td>
                <td class="p-3 text-xs">
                    <button onclick="event.stopPropagation(); selectRegion('${item.short}'); switchTab('tab-summary');" class="bg-white hover:bg-rose-50 text-rose-600 border border-rose-200 px-2.5 py-1 rounded-lg text-xs font-bold transition shadow-2xs">
                        상세 분석 >
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function onBenchmarkRowClick(shortName) {
    selectRegion(shortName);
}

// 5. 트리맵 / 비례 타일맵 렌더링 (클릭 시 풀네임 및 자동 이동)
function renderTreemap() {
    const grid = document.getElementById('treemap-grid');
    if (!grid) return;

    const sorted = Object.entries(REGION_DATA).sort((a, b) => b[1].exp - a[1].exp);

    grid.innerHTML = sorted.map(([reg, d]) => {
        const full = FULL_NAME_MAP[reg];
        let bgClass = 'bg-blue-50 border-blue-200 text-blue-900';
        let badgeColor = 'bg-blue-100 text-blue-800';
        if (d.sat >= 81.0) {
            bgClass = 'bg-emerald-50 border-emerald-300 text-emerald-950';
            badgeColor = 'bg-emerald-100 text-emerald-800';
        } else if (d.sat < 79.0) {
            bgClass = 'bg-amber-50 border-amber-300 text-amber-950';
            badgeColor = 'bg-amber-100 text-amber-800';
        }

        return `
            <div onclick="selectRegion('${reg}'); switchTab('tab-summary');" class="cursor-pointer p-3.5 rounded-xl border ${bgClass} hover:shadow-md transition flex flex-col justify-between">
                <div class="flex items-center justify-between">
                    <span class="font-black text-xs sm:text-sm text-[#0b1b3d]">${full}</span>
                    <span class="text-[10px] font-bold px-1.5 py-0.5 rounded ${badgeColor}">${d.sat}점</span>
                </div>
                <div class="mt-2.5">
                    <div class="text-[10px] text-slate-500 font-semibold">1인 평균 지출액</div>
                    <div class="text-sm sm:text-base font-extrabold">${formatWon(d.exp)}</div>
                </div>
                <div class="mt-2 text-[10px] text-slate-400 flex items-center justify-between border-t border-slate-200/60 pt-1.5">
                    <span>재방문: ${d.reb}점</span>
                    <span class="text-[#00a3e0] font-bold">분석 ></span>
                </div>
            </div>
        `;
    }).join('');
}

// 6. 콤보 추세 차트 렌더링 (원 단위)
function renderComboChart() {
    const canvas = document.getElementById('comboTrendChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (comboTrendChart) comboTrendChart.destroy();

    const shortLabels = Object.keys(REGION_DATA);
    const fullLabels = shortLabels.map(r => FULL_NAME_MAP[r]);
    const expDataInWon = shortLabels.map(r => Math.round(REGION_DATA[r].exp * 1000));
    const satData = shortLabels.map(r => REGION_DATA[r].sat);

    comboTrendChart = new Chart(ctx, {
        data: {
            labels: fullLabels,
            datasets: [
                {
                    type: 'bar',
                    label: '1인 평균 지출액 (원)',
                    data: expDataInWon,
                    backgroundColor: '#00a3e0',
                    yAxisID: 'yExp',
                    borderRadius: 4,
                    order: 2
                },
                {
                    type: 'line',
                    label: '전반적 만족도 점수 (100점 만점)',
                    data: satData,
                    borderColor: '#f97316',
                    backgroundColor: '#f97316',
                    borderWidth: 2.5,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    yAxisID: 'ySat',
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { font: { size: 11, weight: 'bold' } }
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            if (ctx.datasetIndex === 0) return ` 지출액: ${ctx.parsed.y.toLocaleString()}원`;
                            return ` 만족도: ${ctx.parsed.y}점`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { font: { size: 10, weight: 'bold' } },
                    grid: { display: false }
                },
                yExp: {
                    type: 'linear',
                    position: 'left',
                    title: { display: true, text: '지출액 (원)', font: { size: 11, weight: 'bold' } },
                    grid: { color: '#f1f5f9' },
                    ticks: {
                        callback: (v) => `${(v / 10000).toFixed(0)}만원`
                    }
                },
                ySat: {
                    type: 'linear',
                    position: 'right',
                    title: { display: true, text: '만족도 (점)', font: { size: 11, weight: 'bold' } },
                    min: 75,
                    max: 85,
                    grid: { display: false }
                }
            }
        }
    });
}

// 7. Top 5 순위 위젯 렌더링
function renderTop5Widgets() {
    // 1) 만족도 Top 5
    const satSorted = Object.entries(REGION_DATA)
        .map(([reg, d]) => ({ reg, full: FULL_NAME_MAP[reg], sat: d.sat, exp: d.exp }))
        .sort((a, b) => b.sat - a.sat)
        .slice(0, 5);

    const satListElem = document.getElementById('top5-satisfaction-list');
    if (satListElem) {
        satListElem.innerHTML = satSorted.map((item, idx) => `
            <div onclick="selectRegion('${item.reg}'); switchTab('tab-summary');" class="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 cursor-pointer border border-slate-100 transition">
                <div class="flex items-center gap-3">
                    <span class="w-6 h-6 rounded-md bg-amber-100 text-amber-800 font-black text-xs flex items-center justify-center">${idx + 1}</span>
                    <span class="font-extrabold text-xs text-slate-800">${item.full}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="font-black text-xs text-emerald-600">${item.sat}점</span>
                    <span class="text-[11px] text-slate-400">(${formatWon(item.exp)})</span>
                </div>
            </div>
        `).join('');
    }

    // 2) 최고 가성비 Top 5
    const vfmSorted = Object.entries(REGION_DATA)
        .map(([reg, d]) => ({ reg, full: FULL_NAME_MAP[reg], vfm: (d.sat / d.exp).toFixed(2), sat: d.sat, exp: d.exp }))
        .sort((a, b) => b.vfm - a.vfm)
        .slice(0, 5);

    const vfmListElem = document.getElementById('top5-vfm-list');
    if (vfmListElem) {
        vfmListElem.innerHTML = vfmSorted.map((item, idx) => `
            <div onclick="selectRegion('${item.reg}'); switchTab('tab-summary');" class="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 cursor-pointer border border-slate-100 transition">
                <div class="flex items-center gap-3">
                    <span class="w-6 h-6 rounded-md bg-emerald-100 text-emerald-800 font-black text-xs flex items-center justify-center">${idx + 1}</span>
                    <span class="font-extrabold text-xs text-slate-800">${item.full}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="font-black text-xs text-[#00a3e0]">효율 ${item.vfm}</span>
                    <span class="text-[11px] text-slate-400">(${formatWon(item.exp)})</span>
                </div>
            </div>
        `).join('');
    }
}

// 8. 가성비 4사분면 체류특성 차트 & 표 렌더링
function renderQuadrantMatrix() {
    const canvas = document.getElementById('quadrantMatrixChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (quadrantMatrixChart) quadrantMatrixChart.destroy();

    const quadColors = {
        'Q1_high_high': '#00a3e0',
        'Q2_low_high': '#10b981',
        'Q3_low_low': '#94a3b8',
        'Q4_high_low': '#ef4444'
    };

    const dataset = Object.entries(REGION_DATA).map(([reg, d]) => ({
        x: Math.round(d.exp * 1000),
        y: d.sat,
        region: reg,
        full: FULL_NAME_MAP[reg],
        quad: d.quad
    }));

    quadrantMatrixChart = new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: '17개 광역시도',
                data: dataset,
                backgroundColor: dataset.map(d => quadColors[d.quad]),
                pointRadius: dataset.map(d => d.region === currentRegion ? 9 : 6),
                pointHoverRadius: 9
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const raw = ctx.raw;
                            return ` ${raw.full}: 지출 ${raw.x.toLocaleString()}원, 만족도 ${raw.y}점`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: '1인 평균 지출액 (원) [전국 평균: 53,900원]', font: { weight: 'bold' } },
                    grid: { color: '#f1f5f9' },
                    ticks: {
                        callback: (v) => `${(v / 10000).toFixed(0)}만원`
                    }
                },
                y: {
                    title: { display: true, text: '전반적 만족도 (점) [전국 평균: 80.3점]', font: { weight: 'bold' } },
                    grid: { color: '#f1f5f9' },
                    min: 76,
                    max: 85
                }
            }
        }
    });

    const tbody = document.getElementById('quadrant-tbody');
    if (tbody) {
        const qBadge = {
            'Q1_high_high': '<span class="text-blue-700 bg-blue-50 px-2 py-0.5 rounded text-xs font-semibold">제1사분면: 프리미엄</span>',
            'Q2_low_high': '<span class="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-xs font-semibold">제2사분면: 최고 가성비</span>',
            'Q3_low_low': '<span class="text-slate-700 bg-slate-100 px-2 py-0.5 rounded text-xs font-semibold">제3사분면: 실속형 체류</span>',
            'Q4_high_low': '<span class="text-rose-700 bg-rose-50 px-2 py-0.5 rounded text-xs font-semibold">제4사분면: 비효율 주의</span>'
        };

        tbody.innerHTML = Object.entries(REGION_DATA).map(([reg, d]) => `
            <tr class="hover:bg-slate-50 transition cursor-pointer" onclick="selectRegion('${reg}'); switchTab('tab-summary');">
                <td class="p-3 font-bold text-slate-800">${FULL_NAME_MAP[reg]}</td>
                <td class="p-3 text-slate-600 font-semibold">${formatWon(d.exp)}</td>
                <td class="p-3 text-slate-600 font-semibold">${d.sat}점</td>
                <td class="p-3 font-mono font-bold text-[#00a3e0]">${(d.sat / d.exp).toFixed(2)}</td>
                <td class="p-3">${qBadge[d.quad]}</td>
            </tr>
        `).join('');
    }
}

// 9. 성·연령별 소비 패턴
const AGE_DATA = {
    '전체': {
        topRegions: ['제주특별자치도 (135,000원)', '강원특별자치도 (126,000원)', '경기도 (102,000원)', '전라남도 (72,000원)', '경상남도 (70,000원)'],
        male: [42100, 25400, 18200, 10500, 6800],
        female: [44800, 23100, 19500, 12300, 7900],
        labels: ['외식/음식비', '교통비', '숙박비', '카페/음료', '체험활동비']
    },
    '20대': {
        topRegions: ['제주특별자치도 (142,000원)', '부산광역시 (78,000원)', '강원특별자치도 (115,000원)', '서울특별시 (45,000원)', '전북특별자치도 (51,000원)'],
        male: [38500, 28200, 16500, 12000, 8500],
        female: [42000, 26500, 18000, 15200, 9100],
        labels: ['외식/음식비', '교통비', '숙박비', '카페/음료', '체험활동비']
    },
    '30대': {
        topRegions: ['제주특별자치도 (158,000원)', '강원특별자치도 (139,000원)', '경기도 (112,000원)', '부산광역시 (64,000원)', '경상남도 (81,000원)'],
        male: [45000, 24000, 22100, 11200, 7500],
        female: [46500, 22000, 23500, 13000, 8200],
        labels: ['외식/음식비', '교통비', '숙박비', '카페/음료', '체험활동비']
    },
    '40대': {
        topRegions: ['강원특별자치도 (142,000원)', '제주특별자치도 (140,000원)', '경기도 (125,000원)', '경상북도 (85,000원)', '전라남도 (82,000원)'],
        male: [48200, 22500, 20100, 8900, 6500],
        female: [47500, 21000, 21500, 10500, 7000],
        labels: ['외식/음식비', '교통비', '숙박비', '카페/음료', '체험활동비']
    },
    '50대': {
        topRegions: ['전라남도 (95,000원)', '강원특별자치도 (130,000원)', '경상북도 (89,000원)', '경상남도 (88,000원)', '제주특별자치도 (121,000원)'],
        male: [50100, 21000, 17500, 7500, 5800],
        female: [49000, 20500, 18200, 8200, 6200],
        labels: ['외식/음식비', '교통비', '숙박비', '카페/음료', '체험활동비']
    },
    '60대이상': {
        topRegions: ['전라남도 (92,000원)', '경상북도 (84,000원)', '강원특별자치도 (118,000원)', '경상남도 (82,000원)', '충청남도 (68,000원)'],
        male: [51500, 19500, 16000, 6200, 4800],
        female: [52000, 18500, 16500, 6800, 5000],
        labels: ['외식/음식비', '교통비', '숙박비', '카페/음료', '체험활동비']
    }
};

function selectAgeTab(groupKey) {
    document.querySelectorAll('.age-tab-btn').forEach(b => {
        if (b.innerText.trim() === groupKey) b.classList.add('active');
        else b.classList.remove('active');
    });

    const data = AGE_DATA[groupKey] || AGE_DATA['전체'];
    const titleElem = document.getElementById('age-top-title');
    if (titleElem) titleElem.innerText = groupKey;

    const listElem = document.getElementById('age-top-regions-list');
    if (listElem) {
        listElem.innerHTML = data.topRegions.map((item, idx) => `
            <div class="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-200/60 text-xs">
                <span class="font-bold text-slate-700">0${idx + 1}. ${item.split(' ')[0]}</span>
                <span class="text-rose-600 font-extrabold text-[11px]">${item.split(' ')[1]}</span>
            </div>
        `).join('');
    }

    renderAgePyramid(data);
}

function renderAgePyramid(data) {
    const canvas = document.getElementById('agePyramidChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (agePyramidChart) agePyramidChart.destroy();

    agePyramidChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: '남성 평균 지출 (원)',
                    data: data.male.map(v => -v),
                    backgroundColor: '#00a3e0',
                    borderRadius: 4
                },
                {
                    label: '여성 평균 지출 (원)',
                    data: data.female,
                    backgroundColor: '#f97316',
                    borderRadius: 4
                }
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.dataset.label}: ${Math.abs(ctx.parsed.x).toLocaleString()}원`
                    }
                },
                legend: { display: false }
            },
            scales: {
                x: {
                    ticks: {
                        callback: (v) => `${(Math.abs(v) / 1000).toLocaleString()}천원`
                    },
                    grid: { color: '#f1f5f9' }
                },
                y: { grid: { display: false } }
            }
        }
    });
}

// 10. 탭 전환
function switchTab(tabId) {
    if (tabId === 'tab-compare') {
        switchTab('tab-summary');
        const benchSec = document.getElementById('benchmark-section');
        if (benchSec) {
            benchSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        loadRegionalBenchmark();
        return;
    }

    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

    const targetTab = document.getElementById(tabId);
    if (targetTab) targetTab.classList.remove('hidden');

    const targetBtn = document.getElementById(`btn-${tabId}`);
    if (targetBtn) targetBtn.classList.add('active');

    if (tabId === 'tab-summary') {
        loadRegionalBenchmark();
    }
    if (tabId === 'tab-trend' && comboTrendChart) comboTrendChart.resize();
    if (tabId === 'tab-quadrant' && quadrantMatrixChart) quadrantMatrixChart.resize();
    if (tabId === 'tab-age' && agePyramidChart) agePyramidChart.resize();
}

// 11. 원천 데이터셋 관리 & 사용자 CSV 업로드
async function initDatasets() {
    try {
        const res = await fetch('/api/datasets');
        const data = await res.json();
        if (data.success) {
            datasets = data.datasets;
            renderDatasetTable();
            const badge = document.getElementById('datasets-count-badge');
            if (badge) badge.innerText = `총 ${datasets.length}개 데이터셋 정상 운용 중`;
        }
    } catch (e) {
        console.error('데이터셋 목록 로드 오류:', e);
    }
}

function renderDatasetTable() {
    const tbody = document.getElementById('dataset-table-body');
    if (!tbody) return;
    tbody.innerHTML = datasets.map(d => `
        <tr class="hover:bg-slate-50 transition">
            <td class="p-3 font-semibold text-slate-800 flex items-center gap-2">
                <i class="fa-solid fa-file-csv text-emerald-600 text-sm"></i> ${d.filename}
            </td>
            <td class="p-3">
                ${d.is_regional ? '<span class="text-xs bg-blue-50 text-blue-700 font-semibold px-2 py-0.5 rounded-full">전국 17개 광역시도 전수</span>' : '<span class="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">지출 항목별 비중</span>'}
            </td>
            <td class="p-3 text-slate-600 text-xs">${d.sub_items ? d.sub_items.length + '개 세부항목' : '-'}</td>
            <td class="p-3">
                <span class="text-xs text-emerald-600 font-semibold flex items-center gap-1">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> 정상 운용 중
                </span>
            </td>
        </tr>
    `).join('');
}

async function handleDatasetUpload(e) {
    e.preventDefault();
    const fileInput = document.getElementById('dataset-file-input');
    const statusMsg = document.getElementById('upload-status-msg');
    const submitBtn = document.getElementById('btn-upload-dataset');

    if (!fileInput.files || fileInput.files.length === 0) {
        alert('업로드할 CSV 파일을 선택해 주세요.');
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 파일 분석 및 검증 중...';
    statusMsg.classList.remove('hidden', 'text-emerald-600', 'text-rose-600');
    statusMsg.innerText = 'CSV 데이터를 파싱하고 광역시도 행정구역을 검증하는 중입니다...';

    try {
        const res = await fetch('/api/upload-dataset', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            statusMsg.classList.add('text-emerald-600');
            statusMsg.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${data.message} (세부항목 ${data.dataset.sub_items_count}개 감지됨)`;
            fileInput.value = '';
            initDatasets();
        } else {
            statusMsg.classList.add('text-rose-600');
            statusMsg.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> 업로드 실패: ${data.error}`;
        }
    } catch (err) {
        statusMsg.classList.add('text-rose-600');
        statusMsg.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> 서버 통신 오류: ${err.message}`;
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> 데이터셋 탑재';
    }
}

// 12. 공통 기능 (마이데이터 추가, 차트 저장, CSV 다운로드, 아코디언 토글)
function addToMyDataLab() {
    alert(`[분석 보관함] '${getFullName(currentRegion)}'의 관광 지출(원) & 만족도 지표가 보관함에 추가되었습니다.`);
}

function saveChartImage() {
    const canvas = document.querySelector('.tab-content:not(.hidden) canvas');
    if (!canvas) {
        alert('현재 화면에 저장할 수 있는 차트가 없습니다.');
        return;
    }
    const link = document.createElement('a');
    link.download = `관광데이터분석_${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
}

function saveComboChartImage() {
    const canvas = document.getElementById('comboTrendChart');
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `지출_만족도_콤보차트_${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
}

function saveQuadrantChartImage() {
    const canvas = document.getElementById('quadrantMatrixChart');
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `가성비_4사분면_매트릭스_${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
}

function downloadDatasetCSV() {
    let csv = "지역명,1인_평균_지출액(원),전반적_만족도(100점),재방문_의향,관광지_물가만족도,사분면_분류\n";
    Object.entries(REGION_DATA).forEach(([reg, d]) => {
        const full = FULL_NAME_MAP[reg];
        const won = Math.round(d.exp * 1000);
        csv += `"${full}","${won}","${d.sat}","${d.reb}","${d.cost}","${d.quad}"\n`;
    });
    const blob = new Blob(["\uFEFF" + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `한국관광지_데이터분석_실측전수_N17_원단위.csv`;
    link.click();
}

function toggleDataDescription() {
    const body = document.getElementById('data-description-body');
    const arrow = document.getElementById('accordion-arrow');
    if (body.classList.contains('hidden')) {
        body.classList.remove('hidden');
        arrow.style.transform = 'rotate(180deg)';
    } else {
        body.classList.add('hidden');
        arrow.style.transform = 'rotate(0deg)';
    }
}

function refreshCurrentView() {
    const val = document.getElementById('global-region-select').value;
    if (val === '전국') {
        switchTab('tab-treemap');
    } else {
        selectRegion(val);
        switchTab('tab-summary');
    }
}

// 13. AI 데이터랩 질의응답
async function handleChatSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    const input = document.getElementById('chat-input');
    if (!input) return;
    const msg = input.value.trim();
    if (!msg) return;

    input.value = '';
    appendChatMessage('user', msg);
    const loadingId = appendChatMessage('ai', '본 사이트 탑재 데이터 분석 중...');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ message: msg })
        });
        const data = await res.json();
        const loadingElem = document.getElementById(loadingId);
        if (loadingElem) {
            loadingElem.innerHTML = formatMarkdownToHtml(data.reply || data.error);
        }
    } catch (err) {
        const loadingElem = document.getElementById(loadingId);
        if (loadingElem) {
            loadingElem.innerText = `답변 생성 중 오류가 발생했습니다: ${err.message}`;
        }
    }
}

async function sendQuickChat(prompt) {
    const input = document.getElementById('chat-input');
    if (input) input.value = prompt;
    switchTab('tab-chat');
    const chatContainer = document.getElementById('chat-messages');
    if (chatContainer) {
        chatContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    await handleChatSubmit();
}

function appendChatMessage(sender, text) {
    const chatContainer = document.getElementById('chat-messages');
    const msgId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;

    const wrapper = document.createElement('div');
    wrapper.className = `flex gap-2.5 ${sender === 'user' ? 'justify-end' : ''}`;

    if (sender === 'user') {
        wrapper.innerHTML = `
            <div class="chat-bubble-user p-3.5 text-xs max-w-xl leading-relaxed">
                ${escapeHtml(text)}
            </div>
            <div class="w-8 h-8 rounded-xl bg-slate-800 text-white flex items-center justify-center text-xs shrink-0 font-bold">나</div>
        `;
    } else {
        wrapper.innerHTML = `
            <img src="/static/ikon.png" alt="AI" class="w-8 h-8 rounded-xl object-cover shadow-2xs shrink-0 border border-slate-200">
            <div id="${msgId}" class="chat-bubble-ai p-3.5 text-xs text-slate-700 max-w-2xl leading-relaxed">
                ${formatMarkdownToHtml(text)}
            </div>
        `;
    }

    chatContainer.appendChild(wrapper);
    chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
    return msgId;
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatMarkdownToHtml(str) {
    return str
        .replace(/### (.*)/g, '<h4 class="font-bold text-[#0b1b3d] text-xs mt-2 mb-1">$1</h4>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code class="bg-blue-50 text-blue-700 px-1 py-0.5 rounded text-[11px] font-mono">$1</code>')
        .replace(/> ⚠️ (.*)/g, '<div class="p-2.5 bg-amber-50 text-amber-900 border border-amber-300 rounded-lg text-xs my-1 font-semibold">⚠️ $1</div>')
        .replace(/(https:\/\/kosis\.kr[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline font-bold hover:text-blue-800">$1</a>')
        .replace(/\n- (.*)/g, '<li class="ml-3 list-disc text-slate-700 text-xs my-0.5">$1</li>')
        .replace(/\n/g, '<br>');
}
