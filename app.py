# -*- coding: utf-8 -*-
"""
Travel Cost & Satisfaction Insight Builder - Flask Web Application (app.py)
규칙:
- 모든 계산은 Pandas/Numpy가 수행하며 Gemini에게 계산을 시키지 않는다.
- Gemini에게 원본 CSV 전체를 보내지 않고 계산된 결과만 전달한다.
- logging 모듈을 사용하며 print()를 사용하지 않는다.
- API Key는 프론트엔드에 절대 노출하지 않는다.
"""
import os
import io
import re
import json
import logging
import traceback
from datetime import datetime
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template

from tools import TOOL_CATALOG, sanitize_dict, safe_number, is_aggregate_row

# 환경변수 로드
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

# 로깅 설정 (정해진 포맷)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("TravelInsightBuilder")

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024

# 메모리 내 1개 데이터셋만 보관 (디스크 영구 저장 안 함)
CURRENT_DATASET = {
    "df": None,
    "filename": None,
    "diagnosis": None,
    "last_run_result": None
}

# 여행 데이터 열 역할 판별 키워드
PLACE_KEYWORDS = ['지역', '여행지', '시도', '도시', '국가', '관광지', 'city', 'country', 'region', 'destination', 'place', 'location']
COST_KEYWORDS = ['지출', '비용', '물가', '숙박비', '식비', '교통비', '식음료', '금액', '가격', 'cost', 'price', 'expense', 'expenditure', 'fee']
SAT_KEYWORDS = ['만족', '만족도', '재방문', '추천', '평점', '점수', 'satisfaction', 'score', 'rating', 'revisit', 'recommend']
PERIOD_KEYWORDS = ['연도', '년도', '시점', '분기', '월', '일자', 'year', 'date', 'period', 'month', 'time']


def try_parse_csv(file_bytes: bytes, filename: str):
    """
    인코딩 4개 순차 시도(utf-8-sig, utf-8, cp949, euc-kr)
    헤더 위치 자동 감지
    """
    logger.info(f"[REQUEST] POST /inspect")
    logger.info(f"[FILE] name={filename} size={len(file_bytes)} bytes")

    encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']
    decoded_text = None
    success_enc = None

    for enc in encodings:
        try:
            decoded_text = file_bytes.decode(enc)
            success_enc = enc
            logger.info(f"[ENCODING] {enc} 성공")
            break
        except UnicodeDecodeError:
            logger.info(f"[ENCODING] {enc} 실패, 다음 인코딩 시도")
            continue

    if not decoded_text or not success_enc:
        logger.error("[ERROR] 지원되는 모든 인코딩(utf-8-sig, utf-8, cp949, euc-kr) 시도 실패")
        raise ValueError("파일의 인코딩을 인식할 수 없습니다. UTF-8 또는 CP949 형식인지 확인해 주세요.")

    lines = [l for l in decoded_text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("파일 내용이 비어 있습니다.")

    # 헤더 행 찾기 (앞쪽 10줄 검사)
    header_idx = 0
    max_cols = 0
    for i in range(min(10, len(lines))):
        parts = [p.strip().replace('"', '') for p in lines[i].split(',')]
        # 비어있지 않은 문자열이 많고 의미 있는 열 이름처럼 보이는 행 탐색
        valid_parts = [p for p in parts if p and not p.isdigit()]
        if len(valid_parts) > max_cols:
            max_cols = len(valid_parts)
            header_idx = i

    skipped_lines = header_idx
    logger.info(f"[HEADER] 감지 완료: header_row={header_idx}, skipped_lines={skipped_lines}")

    # DataFrame 로드
    csv_io = io.StringIO("\n".join(lines[header_idx:]))
    df = pd.read_csv(csv_io)

    # 열 이름 정제 (공백 제거)
    df.columns = [str(c).strip() for c in df.columns]

    logger.info(f"[CSV] parsing 완료 rows={len(df)} columns={len(df.columns)}")
    return df, success_enc, skipped_lines


def diagnose_dataframe(df: pd.DataFrame, filename: str, file_size: int, success_enc: str, skipped_lines: int):
    """여행 데이터 13개 항목 진단 로직"""
    n_rows, n_cols = df.shape
    col_names = list(df.columns)
    col_dtypes = {c: str(df[c].dtype) for c in col_names}

    # 1. Unnamed / 빈 열 감지
    unnamed_cols = [c for c in col_names if 'unnamed' in c.lower() or c == '' or df[c].dropna().empty]
    
    # 2. 결측치 및 중복
    missing_info = {}
    for c in col_names:
        cnt = int(df[c].isnull().sum())
        missing_info[c] = {
            "count": cnt,
            "ratio_pct": round((cnt / n_rows) * 100, 2) if n_rows > 0 else 0
        }
    duplicate_rows = int(df.duplicated().sum())

    # 3. 열 역할 자동 분류
    place_candidates = []
    cost_candidates = []
    sat_candidates = []
    period_candidates = []

    for c in col_names:
        c_lower = c.lower()
        is_num = pd.api.types.is_numeric_dtype(df[c]) or (pd.to_numeric(df[c], errors='coerce').notnull().sum() > n_rows * 0.5)

        # 시점
        if any(k in c_lower for k in PERIOD_KEYWORDS):
            period_candidates.append(c)
        # 물가/비용
        elif any(k in c_lower for k in COST_KEYWORDS) and is_num:
            cost_candidates.append(c)
        # 만족도
        elif any(k in c_lower for k in SAT_KEYWORDS) and is_num:
            sat_candidates.append(c)
        # 여행지/지역
        elif any(k in c_lower for k in PLACE_KEYWORDS) or (not is_num and df[c].nunique() > 2):
            place_candidates.append(c)

    # 후보가 없을 때 숫자형 열을 비용/만족도 후보로 폴백 배정
    numeric_cols = [c for c in col_names if pd.api.types.is_numeric_dtype(df[c]) or (pd.to_numeric(df[c], errors='coerce').notnull().sum() > n_rows * 0.5)]
    if not cost_candidates and numeric_cols:
        cost_candidates.append(numeric_cols[0])
    if not sat_candidates and len(numeric_cols) > 1:
        sat_candidates.append(numeric_cols[1])
    if not place_candidates:
        non_num = [c for c in col_names if c not in numeric_cols]
        if non_num:
            place_candidates.append(non_num[0])

    # 4. 시점 충실도 및 권장 기준시점
    period_coverage = {}
    recommended_period = "ALL (단일 시점)"
    if period_candidates:
        p_col = period_candidates[0]
        p_counts = df[p_col].astype(str).value_counts().to_dict()
        period_coverage = p_counts
        # 가장 최근이거나 빈도 높은 시점
        sorted_p = sorted(p_counts.items(), key=lambda x: str(x[0]), reverse=True)
        if sorted_p:
            recommended_period = str(sorted_p[0][0])

    # 5. 집계 행 후보
    aggregate_candidates = []
    for idx, row in df.iterrows():
        if is_aggregate_row(row):
            label = str(row.iloc[0]) if len(row) > 0 else f"Row {idx}"
            aggregate_candidates.append({"index": int(idx), "label": label})

    # 6. 경고 목록
    warnings = []
    if n_rows < 5:
        warnings.append(f"표본 수(행 수 {n_rows}개)가 5개 미만으로 너무 적어 통계 분석 시 왜곡 위험이 있습니다.")
    if len(numeric_cols) < 2:
        warnings.append("물가와 만족도를 교차 비교할 수 있는 숫자형 열이 2개 이상 필요합니다.")
    if unnamed_cols:
        warnings.append(f"이름이 없거나 빈 열이 감지되었습니다: {', '.join(unnamed_cols)}")
    if duplicate_rows > 0:
        warnings.append(f"중복된 행이 {duplicate_rows}개 존재합니다.")
    if aggregate_candidates:
        warnings.append(f"집계성 행(전국, 전체, 합계 등) {len(aggregate_candidates)}개가 감지되었습니다. 분석 시 제외를 권장합니다.")

    # 7. 미리보기 10행
    preview_rows = df.head(10).replace({np.nan: None}).to_dict(orient='records')

    diagnosis = {
        "filename": filename,
        "file_size": file_size,
        "encoding": success_enc,
        "skipped_lines": skipped_lines,
        "rows": n_rows,
        "columns": n_cols,
        "column_names": col_names,
        "dtypes": col_dtypes,
        "role_candidates": {
            "place": place_candidates,
            "cost": cost_candidates,
            "satisfaction": sat_candidates,
            "period": period_candidates
        },
        "missing_info": missing_info,
        "duplicate_rows": duplicate_rows,
        "unnamed_columns": unnamed_cols,
        "period_coverage": period_coverage,
        "recommended_period": recommended_period,
        "aggregate_candidates": aggregate_candidates,
        "preview": preview_rows,
        "warnings": warnings
    }

    logger.info(f"[DIAGNOSE] 진단 완료 warnings={len(warnings)}")
    return diagnosis


# ==========================================
# 라우트 구현
# ==========================================

@app.route('/')
def index():
    """메인 HTML 서빙"""
    return render_template('index.html')


@app.route('/health', methods=['GET'])
def health():
    """서버 상태와 API Key 설정 여부만 반환 (키 값 노출 금지)"""
    has_key = bool(GEMINI_API_KEY and len(GEMINI_API_KEY) > 10)
    return jsonify({
        "status": "ok",
        "has_api_key": has_key,
        "model": GEMINI_MODEL,
        "server_time": datetime.now().isoformat()
    })


@app.route('/inspect', methods=['POST'])
def inspect():
    """CSV 업로드, 인코딩·헤더 감지, 여행 데이터 진단 결과 반환"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "업로드할 CSV 파일을 선택해 주세요."}), 400

    file = request.files['file']
    filename = file.filename or "uploaded.csv"

    if not filename.lower().endswith('.csv'):
        return jsonify({"success": False, "error": "허용되는 파일 확장자는 .csv 입니다."}), 400

    try:
        file_bytes = file.read()
        if len(file_bytes) == 0:
            return jsonify({"success": False, "error": "빈 파일입니다. 데이터가 포함된 CSV를 업로드해 주세요."}), 400

        df, enc, skipped = try_parse_csv(file_bytes, filename)
        diagnosis = diagnose_dataframe(df, filename, len(file_bytes), enc, skipped)

        # 메모리에 1개 데이터셋 저장 (디스크 저장 안 함)
        CURRENT_DATASET["df"] = df
        CURRENT_DATASET["filename"] = filename
        CURRENT_DATASET["diagnosis"] = diagnosis
        CURRENT_DATASET["last_run_result"] = None

        return jsonify({"success": True, "diagnosis": diagnosis})

    except Exception as e:
        logger.error(f"[ERROR] inspect 실패: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/suggest', methods=['POST'])
def suggest():
    """
    진단 결과를 Gemini에 전달하고 도구 카탈로그 중 3~5개 제안을 JSON으로 수신
    규칙: 카탈로그 내 도구만 제안, 물가-만족도 연계 분석 우선 제안, 순수 JSON만 반환
    """
    logger.info("[REQUEST] POST /suggest")
    if CURRENT_DATASET["df"] is None or CURRENT_DATASET["diagnosis"] is None:
        return jsonify({"success": False, "error": "먼저 CSV 파일을 업로드하여 진단을 완료해 주세요."}), 400

    diag = CURRENT_DATASET["diagnosis"]
    roles = diag["role_candidates"]
    cost_col = roles["cost"][0] if roles["cost"] else None
    sat_col = roles["satisfaction"][0] if roles["satisfaction"] else None
    place_col = roles["place"][0] if roles["place"] else (diag["column_names"][0] if diag["column_names"] else "지역")
    period_col = roles["period"][0] if roles["period"] else None
    ref_period = diag["recommended_period"]

    prompt = f"""
당신은 관광통계 데이터 분석 전문가입니다.
사용자가 업로드한 여행 데이터의 진단 요약은 다음과 같습니다:
- 파일명: {diag['filename']} (행 {diag['rows']}개, 열 {diag['columns']}개)
- 열 목록: {diag['column_names']}
- 감지된 여행지 열 후보: {roles['place']}
- 감지된 물가/비용 열 후보: {roles['cost']}
- 감지된 만족도 열 후보: {roles['satisfaction']}
- 감지된 시점 열 후보: {roles['period']}
- 권장 기준시점: {ref_period}

아래는 실행 가능한 12개 도구 카탈로그입니다:
1. reshape_wide_to_long: 연도/시점별 가로 열을 세로 행으로 접기
2. quality_report: 결측·중복·타입·이상치 진단
3. period_coverage: 시점별 값 개수 및 권장 기준시점
4. detect_aggregates: 전국/합계 등 집계 행 탐지
5. describe_numeric: 주요 숫자 열 기술통계(평균, 사분위수 등)
6. trend_line: 선택 여행지들의 시점별 물가/만족도 추이
7. top_bottom_n: 기준시점 지표 상하위 N개 여행지
8. cost_bracket_satisfaction: 물가 구간(저/중/고물가)별 평균 만족도 비교
9. value_for_money_rank: 가성비 지수(만족도÷물가) 상하위 순위
10. distribution: 물가 또는 만족도 점수의 구간별 분포
11. correlation_scatter: 물가(X)와 만족도(Y)의 상관분석(r, R²) 및 4사분면 분류
12. compare_one_vs_all: 특정 여행지 vs 전체 평균 비교

[제안 규칙]
1. 도구 카탈로그에 존재하는 도구만 사용하십시오.
2. 데이터셋에 실제로 존재하는 열 이름만 파라미터에 넣으십시오.
3. 물가 열과 만족도 열이 모두 있는 경우, 두 지표를 연계하는 도구(correlation_scatter, value_for_money_rank, cost_bracket_satisfaction)를 반드시 우선 포함하십시오.
4. 3개에서 5개의 제안을 생성하십시오.
5. 마크다운 따옴표(```json 등) 없이 오직 순수한 JSON 객체만 출력하십시오.

출력 JSON 형식:
{{
  "suggestions": [
    {{
      "tool": "도구명",
      "params": {{ ... }},
      "reference_period": "{ref_period}",
      "why": "제안 이유",
      "caution": "주의사항"
    }}
  ]
}}
"""

    # Gemini API 호출 시도
    if GEMINI_API_KEY:
        try:
            logger.info(f"[AI] suggest 요청 시작 (모델: {GEMINI_MODEL})")
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            raw_text = response.text.strip()
            logger.info(f"[AI] suggest 응답 수신 길이: {len(raw_text)}")

            # JSON 파싱
            clean_json = re.sub(r'^```json\s*', '', raw_text)
            clean_json = re.sub(r'^```\s*', '', clean_json)
            clean_json = re.sub(r'```$', '', clean_json).strip()

            parsed = json.loads(clean_json)
            if "suggestions" in parsed and len(parsed["suggestions"]) > 0:
                logger.info(f"[AI] suggest JSON 파싱 성공 ({len(parsed['suggestions'])}개 제안)")
                return jsonify({"success": True, "source": "gemini", "suggestions": parsed["suggestions"]})
        except Exception as e:
            logger.error(f"[ERROR] Gemini suggest 실패, 폴백 제안 제공: {e}")

    # API 키가 없거나 실패한 경우의 규칙 기반 표준 제안 폴백
    logger.info("[AI] 규칙 기반 표준 제안(Fallback) 생성")
    fallback_suggestions = []

    # 1. 상관분석 (물가 vs 만족도)
    if cost_col and sat_col:
        fallback_suggestions.append({
            "tool": "correlation_scatter",
            "params": {
                "x_column": cost_col,
                "y_column": sat_col,
                "label_column": place_col,
                "reference_period": ref_period,
                "exclude_aggregates": True
            },
            "reference_period": ref_period,
            "why": f"'{cost_col}'(물가/비용)과 '{sat_col}'(만족도)의 피어슨 상관계수(r)를 산출하고 4사분면(가성비 vs 프리미엄)으로 분류합니다.",
            "caution": "상관관계는 인과관계를 의미하지 않으며, 제3의 변수(자연환경, 인프라 등)가 영향을 주었을 수 있습니다."
        })

    # 2. 가성비 순위
    if cost_col and sat_col:
        fallback_suggestions.append({
            "tool": "value_for_money_rank",
            "params": {
                "cost_column": cost_col,
                "satisfaction_column": sat_col,
                "label_column": place_col,
                "reference_period": ref_period,
                "n": 5,
                "exclude_aggregates": True
            },
            "reference_period": ref_period,
            "why": f"평균 대비 적은 비용으로 높은 만족도를 달성한 가성비 우수 여행지 상하위 5곳을 도출합니다.",
            "caution": "단순 비율 지수이므로 절대적인 여행 품질 총량을 온전히 대변하지는 않습니다."
        })

    # 3. 물가 구간별 평균 만족도
    if cost_col and sat_col:
        fallback_suggestions.append({
            "tool": "cost_bracket_satisfaction",
            "params": {
                "cost_column": cost_col,
                "satisfaction_column": sat_col,
                "label_column": place_col,
                "reference_period": ref_period,
                "brackets": 3,
                "exclude_aggregates": True
            },
            "reference_period": ref_period,
            "why": f"물가 수준을 3개 분위(저/중/고물가)로 나누어 각 구간별 평균 만족도 차이를 비교합니다.",
            "caution": "구간 내 지역별 특수성(물가 외 요인)이 상쇄되어 있을 수 있습니다."
        })

    # 4. 상하위 N개
    metric_target = sat_col or cost_col or (diag["column_names"][1] if len(diag["column_names"]) > 1 else None)
    if metric_target:
        fallback_suggestions.append({
            "tool": "top_bottom_n",
            "params": {
                "value_column": metric_target,
                "label_column": place_col,
                "reference_period": ref_period,
                "n": 5,
                "exclude_aggregates": True
            },
            "reference_period": ref_period,
            "why": f"'{metric_target}' 기준 상위 5개 및 하위 5개 여행지를 추출하여 격차를 확인합니다.",
            "caution": f"기준시점({ref_period})에 유효한 데이터만 포함됩니다."
        })

    return jsonify({"success": True, "source": "rule_based", "suggestions": fallback_suggestions})


@app.route('/run', methods=['POST'])
def run_tool():
    """선택된 도구를 Pandas로 실행하고 계산 결과와 차트 데이터 반환"""
    logger.info("[REQUEST] POST /run")
    if CURRENT_DATASET["df"] is None:
        return jsonify({"success": False, "error": "분석할 데이터가 없습니다. CSV를 먼저 업로드해 주세요."}), 400

    payload = request.get_json() or {}
    tool_name = payload.get("tool")
    params = payload.get("params", {})

    if not tool_name or tool_name not in TOOL_CATALOG:
        return jsonify({"success": False, "error": f"도구 목록에 없는 도구입니다: '{tool_name}'"}), 400

    try:
        tool_func = TOOL_CATALOG[tool_name]
        logger.info(f"[TOOL] {tool_name} 실행 시작, params={params}")

        # Pandas로 통계 계산 실행
        calculation_result = tool_func(CURRENT_DATASET["df"], params)

        logger.info(f"[TOOL] 계산 완료: rows_used={calculation_result.get('rows_used')}, rows_excluded={calculation_result.get('rows_excluded')}")

        CURRENT_DATASET["last_run_result"] = calculation_result
        return jsonify({"success": True, "data": calculation_result})

    except ValueError as ve:
        logger.warning(f"[ERROR] 도구 검증 오류: {str(ve)}")
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"[ERROR] 도구 실행 실패: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": f"계산 중 오류가 발생했습니다: {str(e)}"}), 500


@app.route('/explain', methods=['POST'])
def explain():
    """
    /run 계산 결과를 Gemini에 전달하고 통계적 해석 반환
    모드 A: 의도적으로 허술하게 (비교용, Pandas 계산 결과 없이 추상적 보고서)
    모드 B: 정식 (Pandas 계산 결과만 기반으로 7개 엄격 규칙 준수 해석)
    """
    logger.info("[REQUEST] POST /explain")
    payload = request.get_json() or {}
    mode = payload.get("mode", "B").upper()

    if CURRENT_DATASET["df"] is None:
        return jsonify({"success": False, "error": "데이터셋이 없습니다."}), 400

    last_run = CURRENT_DATASET["last_run_result"]
    if not last_run and mode == "B":
        return jsonify({"success": False, "error": "먼저 분석 도구를 실행(/run)해 주세요."}), 400

    diag = CURRENT_DATASET["diagnosis"]

    if mode == "A":
        # 모드 A (비교용, 의도적으로 허술하게): 계산 결과를 주지 않음
        prompt = f"""
이 여행지 물가와 만족도 데이터(파일명: {diag['filename']}, 행 수: {diag['rows']}개)를 분석해서 통계 보고서를 작성해줘.
구체적인 계산 결과는 주지 않았으니 일반적인 지식과 추정으로 작성해줘.
"""
    else:
        # 모드 B (정식): Pandas 계산 결과만 전달
        prompt = f"""
당신은 엄격한 관광통계학 연구자입니다.
아래에 제공된 [Pandas 통계 계산 결과]만을 바탕으로 정밀한 여행 통계 해석 보고서를 작성하십시오.

[절대 규칙]
1. 제공된 계산 결과에 있는 숫자만 인용하십시오. 직접 계산하거나 추정하지 마십시오.
2. 데이터에 없는 여행지·연도·열을 절대 언급하지 마십시오.
3. 기준 시점과 제외된 행 수(및 제외 사유)를 본문에 반드시 명시하십시오.
4. 상관관계를 인과관계로 표현하지 마십시오. (예: "물가가 비싸서 만족도가 올랐다" 금지 -> "물가와 만족도 사이에 양의 상관관계가 관찰되었다"로 표현)
5. 확인할 수 없는 변수(소득, 날씨, 개인 성향 등)는 "이 데이터로는 확인할 수 없다"라고 솔직하게 쓰십시오.
6. 중학생도 이해할 수 있게 통계 용어(상관계수, 결정계수 등)를 쉽게 풀어서 설명하되 정확성을 유지하십시오.

[반드시 준수할 출력 형식 (마크다운 제목 그대로 사용)]:
## 무엇을 봤는가
## 데이터 출처와 지표 정의 (물가·만족도)
## 기준 시점과 제외된 항목
## 통계 계산 결과 요약
## 읽어낼 수 있는 것 (물가와 만족도의 관계)
## 이 데이터로는 알 수 없는 것 (통계적 한계와 숨은 변수)
## 다음에 확인해볼 것

[Pandas 통계 계산 결과]:
{json.dumps(last_run, ensure_ascii=False, indent=2)}
"""

    if not GEMINI_API_KEY:
        # 로컬 규칙 기반 보고서 생성
        logger.info("[AI] Gemini API 키 부재로 로컬 정형화 리포트 생성")
        fallback_report = generate_local_explain_report(mode, last_run, diag)
        return jsonify({"success": True, "mode": mode, "explanation": fallback_report})

    try:
        logger.info(f"[AI] explain 요청 시작 (모드: {mode}, 모델: {GEMINI_MODEL})")
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        report_text = response.text.strip()
        logger.info(f"[AI] explain 응답 수신 성공 (길이: {len(report_text)})")
        return jsonify({"success": True, "mode": mode, "explanation": report_text})

    except Exception as e:
        logger.error(f"[ERROR] Gemini explain 실패, 로컬 리포트로 폴백: {e}")
        fallback_report = generate_local_explain_report(mode, last_run, diag)
        return jsonify({"success": True, "mode": mode, "explanation": fallback_report})


def generate_local_explain_report(mode: str, last_run: dict, diag: dict) -> str:
    """Gemini 호출 실패 또는 API 키 미설정 시 제공하는 엄격 규칙 기반 리포트"""
    if mode == "A":
        return f"""
# [모드 A 보고서 (비교용: 의도적 허술한 모드)]
본 데이터({diag['filename']})는 한국의 관광지별 지출 및 만족도를 나타내는 데이터로 추정됩니다.
전반적으로 물가가 비싼 대도시나 유명 관광지는 시설이 좋아 만족도가 높을 것으로 예상되며, 저렴한 지역은 가성비가 좋을 것입니다. 관광 활성화를 위해 물가 안정이 필요할 것으로 사료됩니다.
*(주의: 이 모드는 Pandas 계산 결과를 전달하지 않아 AI가 통계적 근거 없이 일반론과 추정에 의존하는 현상을 보여주는 교육용 예시입니다.)*
"""
    # 모드 B 정식
    tool = last_run.get("tool", "")
    res = last_run.get("result", {})
    ref = last_run.get("reference_period", "전체")
    r_used = last_run.get("rows_used", 0)
    r_excl = last_run.get("rows_excluded", 0)
    ex_reasons = ", ".join(last_run.get("exclusion_reasons", [])) or "없음"

    lines = [
        f"## 무엇을 봤는가",
        f"- 도구: `{tool}`을 활용하여 `{diag['filename']}` 데이터셋의 통계적 지표를 분석했습니다.",
        f"",
        f"## 데이터 출처와 지표 정의 (물가·만족도)",
        f"- 출처: 사용자가 업로드한 CSV 데이터셋 (`{diag['filename']}`)",
        f"- 분석 대상 열: `{', '.join(last_run.get('columns_used', []))}`",
        f"- 단위: {last_run.get('unit', '실측치')}",
        f"",
        f"## 기준 시점과 제외된 항목",
        f"- **분석 기준 시점**: `{ref}`",
        f"- **사용한 유효 관측치**: `{r_used}개 행`",
        f"- **제외된 행 수**: `{r_excl}개 행` (제외 사유: {ex_reasons})",
        f"",
        f"## 통계 계산 결과 요약"
    ]

    if tool == "correlation_scatter":
        r = res.get('pearson_r')
        r2 = res.get('r_squared')
        formula = res.get('regression_formula')
        q = res.get('quadrants', {})
        q2_places = q.get('Q2_value', {}).get('places', [])
        q1_places = q.get('Q1_premium', {}).get('places', [])

        lines.extend([
            f"- **피어슨 상관계수(r)**: `{r}` ({res.get('strength')}, {res.get('direction')})",
            f"- **결정계수(R²)**: `{r2}` (X축 지표가 Y축 지표 분산의 약 {round(r2*100, 1) if r2 else 0}%를 설명)",
            f"- **OLS 회귀방정식**: `{formula}`",
            f"- **가성비 추천 권역 (2사분면: 저물가·고만족)**: {', '.join(q2_places) if q2_places else '해당 없음'}",
            f"- **프리미엄 권역 (1사분면: 고물가·고만족)**: {', '.join(q1_places) if q1_places else '해당 없음'}"
        ])
    else:
        lines.append(f"- 계산 결과 요약: {json.dumps(res, ensure_ascii=False)}")

    lines.extend([
        f"",
        f"## 읽어낼 수 있는 것 (물가와 만족도의 관계)",
        f"- 실측치 분석 결과, 지정된 기준 시점({ref})에서 수치 간의 관계가 통계적으로 도출되었습니다.",
        f"- {last_run.get('caution', '')}",
        f"",
        f"## 이 데이터로는 알 수 없는 것 (통계적 한계와 숨은 변수)",
        f"- 본 데이터셋에는 관광객 개인의 소득 수준, 방문 당시 날씨, 개별 사업장의 서비스 친절도, 바가지요금의 구체적 원인 등은 포함되어 있지 않으므로 본 통계로는 확인할 수 없습니다.",
        f"- 지역별 소비자물가지수(CPI)는 시계열 가격 변동률 지표이므로 지역 간 절대 가격 수준을 직접 대변하지 않습니다.",
        f"",
        f"## 다음에 확인해볼 것",
        f"- 여행 형태별(당일여행 vs 숙박여행) 지출 세부항목(식비, 숙박비, 교통비)과 만족도 간의 다변량 회귀분석 수행"
    ])

    return "\n".join(lines)


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info(f">> Travel Cost & Satisfaction Insight Builder 가동: http://localhost:5000")
    logger.info(f">> 모델: {GEMINI_MODEL}, API Key 설정 여부: {bool(GEMINI_API_KEY)}")
    logger.info("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=FLASK_DEBUG)
