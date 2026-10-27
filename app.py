# -*- coding: utf-8 -*-
"""
Korea Travel Insight Web Application (Flask)
한국 관광지 관련 데이터 분석 - 지역별 관광소비 & 만족도 종합 대시보드
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

import os
import glob
import json
import re
import traceback
from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv

from engine import (
    STANDARD_REGIONS,
    parse_kosis_csv,
    compute_statistics_and_regression
)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

DATA_DIR = os.path.join(os.path.dirname(__file__), 'information')
if not os.path.exists(DATA_DIR):
    DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

DATASETS = {}

def load_initial_datasets():
    csv_files = glob.glob(os.path.join(DATA_DIR, '*.csv'))
    for fpath in csv_files:
        try:
            with open(fpath, 'rb') as f:
                content = f.read()
            fname = os.path.basename(fpath)
            parsed = parse_kosis_csv(content, fname)
            DATASETS[fname] = parsed
        except Exception as e:
            print(f"파일 로드 실패 ({fpath}): {e}")

load_initial_datasets()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'ikon.png', mimetype='image/png')

@app.route('/api/datasets', methods=['GET'])
def list_datasets():
    meta_list = []
    for fname, d in DATASETS.items():
        sub_items = []
        if d.get('is_regional'):
            for rec in d.get('records', []):
                sub_items.append({
                    'category1': rec['category1'],
                    'category2': rec['category2'],
                    'label': rec['sub_label']
                })
        meta_list.append({
            'filename': fname,
            'is_regional': d.get('is_regional', False),
            'type': d.get('type', 'unknown'),
            'sub_items': sub_items,
            'regions': d.get('regions', STANDARD_REGIONS)
        })
    return jsonify({'success': True, 'datasets': meta_list})

@app.route('/api/upload-dataset', methods=['POST'])
def upload_dataset():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '업로드할 파일이 없습니다.'}), 400
    file = request.files['file']
    if not file or not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'error': '.csv 파일만 업로드할 수 있습니다.'}), 400
    try:
        content = file.read()
        fname = file.filename
        parsed = parse_kosis_csv(content, fname)
        DATASETS[fname] = parsed
        return jsonify({
            'success': True,
            'message': f"'{fname}' 파일이 성공적으로 데이터셋에 추가되었습니다.",
            'dataset': {
                'filename': fname,
                'is_regional': parsed.get('is_regional', False),
                'sub_items_count': len(parsed.get('records', [])),
                'regions_count': len(parsed.get('regions', []))
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f"CSV 파싱 오류: {str(e)}"}), 400

REGION_NORMALIZE = {
    '서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구', '인천광역시': '인천',
    '광주광역시': '광주', '대전광역시': '대전', '울산광역시': '울산', '세종특별자치시': '세종',
    '경기도': '경기', '강원특별자치도': '강원', '강원도': '강원',
    '충청북도': '충북', '충청남도': '충남',
    '전북특별자치도': '전북', '전라북도': '전북', '전라남도': '전남',
    '경상북도': '경북', '경상남도': '경남',
    '제주특별자치도': '제주', '제주도': '제주'
}

@app.route('/api/region-summary/<region_name>', methods=['GET'])
def get_region_summary(region_name):
    """
    특정 지역의 소비, 만족도, 재방문, 랭킹 종합 브리핑 반환
    """
    region_name = REGION_NORMALIZE.get(region_name, region_name)
    if region_name not in STANDARD_REGIONS:
        region_name = '제주'

    # 1. 1인 지출액
    exp_ds = next((d for f, d in DATASETS.items() if '지출액' in f), None)
    # 2. 전반적 만족도
    sat_ds = next((d for f, d in DATASETS.items() if '전반적_만족도' in f and '당일' not in f and '숙박' not in f), None)
    # 3. 재방문 의향
    reb_ds = next((d for f, d in DATASETS.items() if '재방문' in f), None)
    # 4. 체감 물가만족도
    cost_ds = next((d for f, d in DATASETS.items() if '물가' in f), None)
    # 5. 당일 vs 숙박 만족도
    day_ds = next((d for f, d in DATASETS.items() if '당일여행_전반적_만족도' in f), None)
    stay_ds = next((d for f, d in DATASETS.items() if '숙박여행_전반적_만족도' in f), None)

    def extract_metric(ds, target_reg):
        if not ds or not ds.get('records'):
            return {'val': None, 'rank': None, 'avg': None, 'diff': None}
        vals = ds['records'][0]['values']
        reg_val = vals.get(target_reg)
        valid = [(r, v) for r, v in vals.items() if v is not None]
        valid.sort(key=lambda x: x[1], reverse=True)
        rank = next((idx + 1 for idx, (r, v) in enumerate(valid) if r == target_reg), None)
        avg = sum(v for r, v in valid) / len(valid) if valid else None
        diff = (reg_val - avg) if (reg_val is not None and avg is not None) else None
        return {'val': reg_val, 'rank': rank, 'avg': round(avg, 2) if avg else None, 'diff': round(diff, 2) if diff else None}

    m_exp = extract_metric(exp_ds, region_name)
    m_sat = extract_metric(sat_ds, region_name)
    m_reb = extract_metric(reb_ds, region_name)
    m_cost = extract_metric(cost_ds, region_name)
    m_day = extract_metric(day_ds, region_name)
    m_stay = extract_metric(stay_ds, region_name)

    # 사분면 판정
    quadrant = "알뜰실속형"
    if m_exp['diff'] is not None and m_sat['diff'] is not None:
        if m_exp['diff'] >= 0 and m_sat['diff'] >= 0:
            quadrant = "고비용·고만족 (프리미엄 체험지)"
        elif m_exp['diff'] < 0 and m_sat['diff'] >= 0:
            quadrant = "저비용·고만족 (최고 가성비 추천지)"
        elif m_exp['diff'] < 0 and m_sat['diff'] < 0:
            quadrant = "저비용·저만족 (경제적 체류지)"
        else:
            quadrant = "고비용·저만족 (비효율 주의 지역)"

    # 구매 항목별 지출 비중 (전국 기준 공식 데이터랩 수치)
    consumption_shares = {
        '음식점비(외식)': 36.7,
        '교통비': 21.3,
        '숙박비': 15.8,
        '식음료비(카페/간식)': 9.2,
        '여행활동비': 5.9,
        '쇼핑비': 4.2,
        '여행회비/기타': 6.9
    }

    return jsonify({
        'success': True,
        'region': region_name,
        'metrics': {
            'expense': m_exp,
            'satisfaction': m_sat,
            'revisit': m_reb,
            'cost_satisfaction': m_cost,
            'day_trip': m_day,
            'stay_trip': m_stay
        },
        'quadrant': quadrant,
        'consumption_shares': consumption_shares
    })

@app.route('/api/overview-matrix', methods=['GET'])
def get_overview_matrix():
    exp_ds = next((d for f, d in DATASETS.items() if '지출액' in f), None)
    sat_ds = next((d for f, d in DATASETS.items() if '전반적_만족도' in f and '당일' not in f and '숙박' not in f), None)
    reb_ds = next((d for f, d in DATASETS.items() if '재방문' in f), None)
    cost_ds = next((d for f, d in DATASETS.items() if '물가' in f), None)

    matrix = []
    if exp_ds and sat_ds:
        s1 = compute_statistics_and_regression(exp_ds['records'][0]['values'], sat_ds['records'][0]['values'], '지출액', '만족도')
        matrix.append({
            'pair': '1인 평균 지출액 ↔ 전반적 만족도',
            'r': s1['pearson_r'], 'r2': s1['r_squared'], 'pval': s1['p_value'], 'sig': s1['significance'],
            'meaning': '지출액이 높을수록 만족도가 비례하여 높아지는 경향 (설명력 약 37.5%)'
        })
    if exp_ds and reb_ds:
        s2 = compute_statistics_and_regression(exp_ds['records'][0]['values'], reb_ds['records'][0]['values'], '지출액', '재방문 의향')
        matrix.append({
            'pair': '1인 평균 지출액 ↔ 향후 재방문 의향',
            'r': s2['pearson_r'], 'r2': s2['r_squared'], 'pval': s2['p_value'], 'sig': s2['significance'],
            'meaning': '지출 규모와 재방문 의향 간 유의미한 양(+)의 상관관계 확인'
        })
    if sat_ds and reb_ds:
        s3 = compute_statistics_and_regression(sat_ds['records'][0]['values'], reb_ds['records'][0]['values'], '만족도', '재방문 의향')
        matrix.append({
            'pair': '전반적 만족도 ↔ 향후 재방문 의향',
            'r': s3['pearson_r'], 'r2': s3['r_squared'], 'pval': s3['p_value'], 'sig': s3['significance'],
            'meaning': '만족도가 높을수록 재방문 의향이 극도로 강력하게 연동됨 (설명력 77.1%)'
        })
    if cost_ds and sat_ds:
        s4 = compute_statistics_and_regression(cost_ds['records'][0]['values'], sat_ds['records'][0]['values'], '물가만족도', '전반적 만족도')
        matrix.append({
            'pair': '관광지 체감 물가만족도 ↔ 전반적 만족도',
            'r': s4['pearson_r'], 'r2': s4['r_squared'], 'pval': s4['p_value'], 'sig': s4['significance'],
            'meaning': '체감 물가 만족도가 전반적인 여행 평가에 긍정적인 기여를 함'
        })

    return jsonify({'success': True, 'matrix': matrix})

@app.route('/api/regional-values', methods=['POST'])
def get_regional_values():
    payload = request.get_json() or {}
    filename = payload.get('filename')
    category1 = payload.get('category1', '전체')
    category2 = payload.get('category2', '소계')

    if filename not in DATASETS:
        return jsonify({'success': False, 'error': '해당 데이터셋을 찾을 수 없습니다.'}), 404

    ds = DATASETS[filename]
    if not ds.get('is_regional'):
        return jsonify({'success': False, 'error': '지역별 통계가 포함되지 않은 데이터셋입니다.'}), 400

    target_rec = None
    for rec in ds['records']:
        if rec['category1'] == category1 and rec['category2'] == category2:
            target_rec = rec
            break
        if not target_rec and rec['sub_label'] == category2:
            target_rec = rec

    if not target_rec and ds['records']:
        target_rec = ds['records'][0]

    vals = target_rec['values']
    valid_items = [{'region': r, 'value': vals.get(r)} for r in STANDARD_REGIONS if vals.get(r) is not None]
    valid_items.sort(key=lambda x: x['value'], reverse=True)

    return jsonify({
        'success': True,
        'filename': filename,
        'label': target_rec['sub_label'],
        'values': vals,
        'ranking': valid_items,
        'n': len(valid_items),
        'missing_regions': [r for r in STANDARD_REGIONS if vals.get(r) is None]
    })

@app.route('/api/correlation-analysis', methods=['POST'])
def analyze_correlation():
    payload = request.get_json() or {}
    x_file = payload.get('x_filename')
    x_cat1 = payload.get('x_cat1', '전체')
    x_cat2 = payload.get('x_cat2', '소계')

    y_file = payload.get('y_filename')
    y_cat1 = payload.get('y_cat1', '전체')
    y_cat2 = payload.get('y_cat2', '소계')

    if x_file not in DATASETS or y_file not in DATASETS:
        return jsonify({'success': False, 'error': '비교할 데이터셋을 선택해 주세요.'}), 400

    ds_x = DATASETS[x_file]
    ds_y = DATASETS[y_file]

    rec_x = next((r for r in ds_x.get('records', []) if (r['category1'] == x_cat1 and r['category2'] == x_cat2) or r['sub_label'] == x_cat2), ds_x['records'][0])
    rec_y = next((r for r in ds_y.get('records', []) if (r['category1'] == y_cat1 and r['category2'] == y_cat2) or r['sub_label'] == y_cat2), ds_y['records'][0])

    x_name = f"{x_file} ({rec_x['sub_label']})"
    y_name = f"{y_file} ({rec_y['sub_label']})"

    stats = compute_statistics_and_regression(rec_x['values'], rec_y['values'], x_name, y_name)
    if 'error' in stats:
        return jsonify({'success': False, 'error': stats['error']})

    return jsonify({
        'success': True,
        'x_name': x_name,
        'y_name': y_name,
        'stats': stats
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    payload = request.get_json() or {}
    query = payload.get('message', '').strip()
    if not query:
        return jsonify({'success': False, 'error': '질문을 입력해 주세요.'}), 400

    if GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            system_context = """
당신은 '한국 관광지 관련 데이터 분석' 전용 AI 어시스턴트입니다.

[답변 절대 원칙 - 엄격 준수]:
1. 반드시 '이 사이트에 탑재된 정보'로만 대답하세요. 이 사이트에 없는 다른 사이트나 외부 임의 지식을 활용해 추가적으로 대답하지 마세요. 다른 사이트를 절대 활용하지 마십시오.
2. 질문에 대해 본 사이트에 수록된 실측 데이터(17개 광역시도 1인 지출액, 만족도, 재방문 의향, 체감 물가만족도, 6대 품목별 지출 비중, 가성비 4사분면, 성·연령별 지출 패턴 등)를 바탕으로 최대한 성실하게 대답하세요.
3. 질문에 대해 본 사이트에서 활용 가능한 정보가 없을 때는 다른 외부 정보를 지어내지 말고, 반드시 아래 문구를 정확히 출력하세요:
   "https://kosis.kr/index/index.do 여기서 찾아서 데이터를 추가해보세요!"
4. 지출액 단위: 반드시 '원' 단위(예: 135,000원, 53,900원, 44,000원, 6,000원)로 표기하세요.
5. 지역 명칭: 반드시 공식 풀네임(충청북도, 충청남도, 전북특별자치도, 전라남도, 경상북도, 경상남도, 강원특별자치도, 경기도, 제주특별자치도, 서울특별시, 부산광역시, 대구광역시, 인천광역시, 광주광역시, 대전광역시, 울산광역시, 세종특별자치시)으로 표기하세요.

[본 사이트 탑재 데이터셋 요약]:
1. 1인 평균 여행 지출액(원):
   - 전국 평균: 53,900원
   - 제주특별자치도: 135,000원 (1위)
   - 강원특별자치도: 126,000원 (2위)
   - 경기도: 102,000원 (3위)
   - 전라남도: 72,000원 (4위)
   - 경상북도 / 경상남도: 70,000원
   - 충청남도: 58,000원
   - 부산광역시: 51,000원
   - 전북특별자치도: 44,000원
   - 서울특별시: 32,000원
   - 충청북도: 31,000원
   - 인천광역시: 20,000원
   - 대구광역시: 13,000원
   - 대전광역시: 12,000원
   - 울산광역시: 8,000원
   - 광주광역시: 6,000원
   - 세종특별자치시: 3,000원
2. 전반적 만족도(100점 만점):
   - 전국 평균: 80.3점
   - 제주특별자치도: 83.2점 (1위)
   - 경상남도: 82.3점 (2위)
   - 부산광역시: 82.0점 (3위)
   - 전라남도: 81.1점 (4위)
   - 강원특별자치도 / 광주광역시: 81.0점
   - 전북특별자치도: 80.5점
   - 충청남도: 80.3점
   - 경상북도: 80.0점
   - 울산광역시: 79.9점
   - 충청북도: 79.6점
   - 서울특별시 / 경기도: 79.1점
   - 대구광역시: 79.0점
   - 인천광역시: 78.4점
   - 세종특별자치시: 78.2점
   - 대전광역시: 77.7점
3. 구매 항목별 지출 비중:
   - 음식점비(외식): 36.7%
   - 교통비: 21.3%
   - 숙박비: 15.8%
   - 식음료비(카페/간식): 9.2%
   - 여행활동비: 5.9%
   - 쇼핑비: 4.2%
   - 여행회비/기타: 6.9%
4. 체감 물가만족도:
   - 전라남도 73.1점, 충청북도 72.8점, 경상남도 72.5점, 충청남도 72.0점, 울산광역시 71.9점, 부산광역시 71.8점, 제주특별자치도 71.6점, 대구광역시 71.2점, 경상북도 71.0점, 강원특별자치도 70.8점, 대전광역시 70.5점, 세종특별자치시 70.1점, 인천광역시 69.5점, 경기도 68.5점, 서울특별시 67.9점
5. 핵심 상관분석:
   - 지출액 vs 만족도: 피어슨 r = 0.6124 (강한 양의 상관관계, p = 0.0090 **)
   - 최고 가성비 지역 (저비용·고만족): 전북특별자치도(44,000원 지출 - 만족도 80.5점), 광주광역시(6,000원 지출 - 만족도 81.0점)
   - 프리미엄 추천 지역 (고비용·고만족): 제주특별자치도(135,000원 - 83.2점), 경상남도(70,000원 - 82.3점), 부산광역시(51,000원 - 82.0점)
"""
            prompt = f"{system_context}\n\n사용자 질문: {query}"
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            return jsonify({'success': True, 'reply': resp.text.strip()})
        except Exception as e:
            print(f"Gemini API 호출 에러: {e}")

    reply = generate_robust_chat_response(query)
    return jsonify({'success': True, 'reply': reply})

def generate_robust_chat_response(query: str) -> str:
    q = query.replace(" ", "")

    if any(k in q for k in ['쓴돈', '지출', '얼마', '만족도알수', '돈과만족', '설문조사', '실제사람']):
        return (
            "### 💡 네, 본 사이트에 탑재된 정보로 실제 쓴 돈과 만족도를 정확히 알 수 있습니다!\n\n"
            "본 사이트의 17개 광역시도 공식 실측 데이터에 수록된 내용은 다음과 같습니다:\n\n"
            "#### 1. 💵 실제 여행객들이 쓴 돈 (1인 평균 지출액)\n"
            "- **전국 평균**: 1인당 **53,900원**\n"
            "- **지출 상위 지역**: **제주특별자치도 (135,000원)**, **강원특별자치도 (126,000원)**, **경기도 (102,000원)**\n"
            "- **지출 하위 지역**: **세종특별자치시 (3,000원)**, **광주광역시 (6,000원)**, **울산광역시 (8,000원)**, **대구광역시 (13,000원)**\n\n"
            "#### 2. ⭐ 설문조사 만족도 (100점 만점)\n"
            "- **전국 평균**: **80.3점**\n"
            "- **만족도 1위 지역**: **제주특별자치도 (83.2점)**\n"
            "- **만족도 최상위권**: **경상남도 (82.3점)**, **부산광역시 (82.0점)**, **전라남도 (81.1점)**, **강원특별자치도 (81.0점)**, **전북특별자치도 (80.5점)**\n"
            "- **상대적 하위권**: 대전광역시 (77.7점), 세종특별자치시 (78.2점), 인천광역시 (78.4점)\n\n"
            "#### 3. 📊 통계적 결론\n"
            "- 상관계수 **$r = +0.6124$ ($p = 0.0090$, 통계적으로 매우 유의)**\n"
            "- 본 사이트 데이터 분석 결과, 지출 규모와 전반적 만족도는 뚜렷한 양(+)의 상관관계를 보입니다."
        )

    if any(k in q for k in ['가성비', '적은예산', '합리적', '어디', '추천', '선택']):
        return (
            "### 🏆 본 사이트 데이터 기반 '최고 가성비' 지역 분석\n\n"
            "본 사이트 17개 시도 데이터 중 **평균 지출액(53,900원)보다 적게 쓰면서 만족도는 전국 평균(80.3점)을 상회한 '저비용·고만족' 지역**입니다:\n\n"
            "1. **🥇 전북특별자치도 (최고 가성비 1순위)**\n"
            "   - 1인 지출액: **44,000원** (전국 평균보다 약 1만원 저렴)\n"
            "   - 전반적 만족도: **80.5점** (전국 평균 80.3점 상회)\n\n"
            "2. **🥈 광주광역시 (최소 지출 고효율)**\n"
            "   - 1인 지출액: **6,000원**\n"
            "   - 전반적 만족도: **81.0점** (전국 5위 수준)\n\n"
            "3. **🥉 경상남도 (적정 비용 고만족)**\n"
            "   - 1인 지출액: **70,000원**\n"
            "   - 전반적 만족도: **82.3점 (전국 2위)**"
        )

    if any(k in q for k in ['숙박비', '식비', '교통비', '밀접', '어떤비용', '항목', '먹는']):
        return (
            "### 🍽️ 본 사이트에 탑재된 '구매 항목별 지출 비중' 통계\n\n"
            "본 사이트의 지출 항목 데이터셋 분석 결과입니다:\n\n"
            "1. **1위: 음식점비 (외식) — 36.7%**\n"
            "2. **2위: 교통비 — 21.3%**\n"
            "3. **3위: 숙박비 — 15.8%**\n"
            "4. **4위: 식음료비 (카페/간식) — 9.2%**\n"
            "5. **5위: 여행활동비 — 5.9%**\n"
            "6. **6위: 쇼핑비 — 4.2%**\n\n"
            "본 사이트 통계상 여행 소비의 36.7%가 외식비에 지출되어 가장 큰 비중을 차지합니다."
        )

    if any(k in q for k in ['물가수준', '물가', '바가지', '비싸']):
        return (
            "### 🔍 본 사이트 탑재 '관광지 체감 물가만족도' 데이터\n\n"
            "- **체감 물가 만족도 1위**: **전라남도 (73.1점)**\n"
            "- **체감 물가 상위권**: **충청북도 (72.8점)**, **경상남도 (72.5점)**, **충청남도 (72.0점)**\n"
            "- **체감 물가 하위권**: **서울특별시 (67.9점)**, **경기도 (68.5점)**, **인천광역시 (69.5점)**, **제주특별자치도 (71.6점)**\n\n"
            "- **분석 시사점**: 제주특별자치도는 체감 물가만족도가 71.6점으로 상대적으로 낮지만, 전반적 종합 만족도는 83.2점으로 전국 1위입니다."
        )

    if any(k in q for k in ['소비자물가', 'cpi', '물가지수']):
        return (
            "### ⚠️ 소비자물가지수(CPI)로 지역 여행 물가를 비교하면 안 되는 이유\n\n"
            "1. **시계열 지표의 한계**: CPI는 각 지역의 기준시점 대비 물가 상승률을 보는 지표이므로, 절대 가격 크기를 나타내지 않습니다.\n"
            "2. **통계적 왜곡 방지**: 지역 간 여행 물가 비교 시에는 본 사이트에 탑재된 **1인 평균 실제 지출액(원)**과 **체감 물가만족도(점)**를 비교해야 합니다."
        )

    # 본 사이트에 활용 가능한 정보가 없을 때 안내
    return (
        f"질문하신 내용: '{query}'\n\n"
        "현재 이 사이트에 수록된 정보(17개 광역시도 지출액, 만족도, 재방문 의향, 품목별 소비 비중 등) 외에 해당 질문에 활용 가능한 정보가 없습니다.\n\n"
        "👉 **https://kosis.kr/index/index.do 여기서 찾아서 데이터를 추가해보세요!**\n\n"
        "(상단 **[8. 원천 데이터셋 관리 & 추가]** 메뉴를 통해 CSV 파일을 업로드하시면 본 사이트에서 바로 연동 분석하실 수 있습니다.)"
    )

if __name__ == '__main__':
    print("=" * 60)
    print(">> Korea Travel Data Lab Server Started: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
