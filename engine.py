# -*- coding: utf-8 -*-
"""
Korea Travel Insight Engine
국내 여행지별 지출액 및 만족도 상관분석·회귀분석·4분면 통계 엔진
"""
import io
import math
import re
import numpy as np
import pandas as pd

STANDARD_REGIONS = [
    '서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종',
    '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'
]

def calculate_student_t_pvalue(t_val: float, df: int) -> float:
    """Scipy 없이 2-tailed Student's t-distribution p-value를 수치 적분으로 계산."""
    if df <= 0 or math.isnan(t_val):
        return 1.0
    t_abs = abs(t_val)
    if t_abs < 1e-12:
        return 1.0
    x = df / (df + t_abs**2)
    a = df / 2.0
    b = 0.5
    steps = 1000
    h = x / steps
    def f(u):
        if u <= 0 or u >= 1:
            return 0.0
        return (u**(a - 1.0)) * ((1.0 - u)**(b - 1.0))
    integral = f(0) + f(x)
    for i in range(1, steps):
        u = i * h
        integral += 4 * f(u) if i % 2 == 1 else 2 * f(u)
    integral *= (h / 3.0)
    beta_const = math.gamma(a) * math.gamma(b) / math.gamma(a + b)
    p_val = max(0.0, min(1.0, integral / beta_const))
    return p_val

def detect_encoding_and_read(content_bytes: bytes) -> str:
    """CP949, EUC-KR, UTF-8-SIG, UTF-8 중 유효한 인코딩 판별"""
    for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
        try:
            return content_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return content_bytes.decode('cp949', errors='ignore')

def parse_kosis_csv(content_bytes: bytes, filename: str):
    """
    KOSIS 및 국민여행조사 CSV 파싱:
    - 2단 헤더(시점, 지역명 또는 항목명) 지원
    - 1단 헤더(지역명, 지출액 등) 지원
    - 결측치 처리('-', '…' 등)
    """
    text = detect_encoding_and_read(content_bytes)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("빈 파일입니다.")

    # 1. 2단 헤더 여부 확인
    first_line = lines[0]
    second_line = lines[1] if len(lines) > 1 else ""

    is_regional_2level = any(r in second_line for r in STANDARD_REGIONS)
    
    if is_regional_2level:
        # 2단 멀티헤더 읽기
        df = pd.read_csv(io.StringIO(text), header=[0, 1])
        # MultiIndex columns 정리
        c0 = [str(col[0]).strip() for col in df.columns]
        c1 = [str(col[1]).strip() for col in df.columns]

        cat1_idx = None
        cat2_idx = None
        for i, (name0, name1) in enumerate(zip(c0, c1)):
            if '통계분류(1)' in name0 or '통계분류(1)' in name1:
                cat1_idx = i
            elif '통계분류(2)' in name0 or '통계분류(2)' in name1:
                cat2_idx = i

        if cat1_idx is None: cat1_idx = 0
        if cat2_idx is None: cat2_idx = 1

        region_cols = {}
        for i, name1 in enumerate(c1):
            for reg in STANDARD_REGIONS:
                if reg == name1:
                    region_cols[reg] = df.columns[i]
                    break

        # 표준화된 레코드 추출
        parsed_records = []
        for _, row in df.iterrows():
            c1_val = str(row.iloc[cat1_idx]).strip()
            c2_val = str(row.iloc[cat2_idx]).strip()
            rec = {
                'category1': c1_val,
                'category2': c2_val,
                'sub_label': f"{c1_val} - {c2_val}" if c1_val != c2_val else c1_val,
                'values': {}
            }
            for reg, col in region_cols.items():
                val_raw = row[col]
                # 결측치 정제
                val_str = str(val_raw).replace(',', '').strip()
                if val_str in ['-', '…', 'X', '', 'nan', 'None']:
                    rec['values'][reg] = None
                else:
                    try:
                        rec['values'][reg] = float(val_str)
                    except ValueError:
                        rec['values'][reg] = None
            parsed_records.append(rec)

        return {
            'filename': filename,
            'type': 'regional_multi_index',
            'is_regional': True,
            'records': parsed_records,
            'regions': list(region_cols.keys()),
            'category_pairs': [(r['category1'], r['category2']) for r in parsed_records]
        }

    # 2. 단일 헤더 형태 (예: 지역, 지출액, 만족도 등 일반 CSV)
    df_single = pd.read_csv(io.StringIO(text))
    col_names = [str(c).strip() for c in df_single.columns]
    
    # 지역 컬럼 찾기
    reg_col = None
    for c in col_names:
        sample_vals = df_single[c].dropna().astype(str).tolist()[:10]
        if any(r in sample_vals for r in STANDARD_REGIONS):
            reg_col = c
            break

    if reg_col:
        # 단일 헤더 지역별 데이터
        numeric_cols = [c for c in col_names if c != reg_col and pd.to_numeric(df_single[c], errors='coerce').notnull().sum() > 3]
        records = []
        for num_col in numeric_cols:
            val_map = {}
            for _, row in df_single.iterrows():
                r_name = str(row[reg_col]).strip()
                matched_reg = None
                for std_r in STANDARD_REGIONS:
                    if std_r in r_name:
                        matched_reg = std_r
                        break
                if matched_reg:
                    try:
                        val_map[matched_reg] = float(str(row[num_col]).replace(',', ''))
                    except (ValueError, TypeError):
                        val_map[matched_reg] = None
            records.append({
                'category1': '일반',
                'category2': num_col,
                'sub_label': num_col,
                'values': val_map
            })
        return {
            'filename': filename,
            'type': 'regional_single_index',
            'is_regional': True,
            'records': records,
            'regions': STANDARD_REGIONS,
            'category_pairs': [('일반', r['category2']) for r in records]
        }

    # 3. 비지역성 (예: 품목별 비중 등)
    return {
        'filename': filename,
        'type': 'non_regional',
        'is_regional': False,
        'records': [],
        'raw_columns': col_names,
        'raw_shape': list(df_single.shape)
    }


def compute_statistics_and_regression(x_data: dict, y_data: dict, x_label: str, y_label: str):
    """
    17개 시도 중 X와 Y가 모두 유효한 지역을 필터링하여 OLS 선형회귀 및 상관분석 수행.
    실제 CSV 데이터만 사용하며 인위적 데이터 생성을 금지함.
    """
    paired_data = []
    excluded_regions = []

    for reg in STANDARD_REGIONS:
        vx = x_data.get(reg)
        vy = y_data.get(reg)
        if vx is not None and vy is not None and not (math.isnan(vx) or math.isnan(vy)):
            paired_data.append({'region': reg, 'x': float(vx), 'y': float(vy)})
        else:
            reason = []
            if vx is None or (isinstance(vx, float) and math.isnan(vx)):
                reason.append(f"{x_label} 결측")
            if vy is None or (isinstance(vy, float) and math.isnan(vy)):
                reason.append(f"{y_label} 결측")
            excluded_regions.append({'region': reg, 'reason': ', '.join(reason)})

    n = len(paired_data)
    if n < 3:
        return {
            'error': f'유효한 관측치(N={n})가 너무 적어 통계 분석(최소 3개 이상 필요)을 진행할 수 없습니다.',
            'n': n,
            'excluded_regions': excluded_regions
        }

    xs = np.array([p['x'] for p in paired_data], dtype=float)
    ys = np.array([p['y'] for p in paired_data], dtype=float)

    mean_x = float(np.mean(xs))
    mean_y = float(np.mean(ys))
    std_x = float(np.std(xs, ddof=1)) if n > 1 else 0.0
    std_y = float(np.std(ys, ddof=1)) if n > 1 else 0.0

    # 1. Pearson 상관계수
    cov_xy = float(np.cov(xs, ys, ddof=1)[0][1]) if n > 1 else 0.0
    if std_x > 0 and std_y > 0:
        pearson_r = cov_xy / (std_x * std_y)
    else:
        pearson_r = 0.0

    # 2. Spearman 순위 상관계수
    rank_x = pd.Series(xs).rank().values
    rank_y = pd.Series(ys).rank().values
    if np.std(rank_x, ddof=1) > 0 and np.std(rank_y, ddof=1) > 0:
        spearman_rho = float(np.cov(rank_x, rank_y, ddof=1)[0][1] / (np.std(rank_x, ddof=1) * np.std(rank_y, ddof=1)))
    else:
        spearman_rho = 0.0

    # 3. OLS 선형회귀 분석 (Y = beta0 + beta1 * X)
    df_resid = n - 2
    if std_x > 0:
        beta1 = cov_xy / (std_x ** 2)
        beta0 = mean_y - beta1 * mean_x
    else:
        beta1 = 0.0
        beta0 = mean_y

    y_pred = beta0 + beta1 * xs
    residuals = ys - y_pred
    ss_tot = float(np.sum((ys - mean_y) ** 2))
    ss_res = float(np.sum(residuals ** 2))
    ss_reg = ss_tot - ss_res

    r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
    adj_r_squared = float(1.0 - ((ss_res / df_resid) / (ss_tot / (n - 1)))) if df_resid > 0 and ss_tot > 0 else 0.0

    # 잔차 표준오차 및 기울기 표준오차
    se_resid = math.sqrt(ss_res / df_resid) if df_resid > 0 else 0.0
    sum_x_dev_sq = float(np.sum((xs - mean_x) ** 2))
    se_beta1 = (se_resid / math.sqrt(sum_x_dev_sq)) if sum_x_dev_sq > 0 else 0.0

    # t-통계량 및 p-value
    t_stat = (beta1 / se_beta1) if se_beta1 > 0 else 0.0
    p_value = calculate_student_t_pvalue(t_stat, df_resid)

    # 유의성 판정
    if p_value < 0.001:
        sig_label = '*** (p < 0.001 고도 유의)'
        is_significant = True
    elif p_value < 0.01:
        sig_label = '** (p < 0.01 매우 유의)'
        is_significant = True
    elif p_value < 0.05:
        sig_label = '* (p < 0.05 유의)'
        is_significant = True
    else:
        sig_label = f'n.s. (p = {p_value:.3f}, 통계적으로 유의하지 않음)'
        is_significant = False

    # 4. 4분면 매트릭스 분류 (X 평균 및 Y 평균 기준)
    quadrants = {
        'Q1_high_high': {'name': '고비용-고만족 (프리미엄)', 'regions': []},
        'Q2_low_high': {'name': '저비용-고만족 (최고 가성비)', 'regions': []},
        'Q3_low_low': {'name': '저비용-저만족 (알뜰실속형)', 'regions': []},
        'Q4_high_low': {'name': '고비용-저만족 (비효율주의)', 'regions': []}
    }

    region_details = []
    for p, pred, res in zip(paired_data, y_pred, residuals):
        reg = p['region']
        rx = p['x']
        ry = p['y']
        
        # 4분면 판정
        if rx >= mean_x and ry >= mean_y:
            q_key = 'Q1_high_high'
        elif rx < mean_x and ry >= mean_y:
            q_key = 'Q2_low_high'
        elif rx < mean_x and ry < mean_y:
            q_key = 'Q3_low_low'
        else:
            q_key = 'Q4_high_low'

        quadrants[q_key]['regions'].append(reg)
        
        # 가성비 지표 (비용 대비 만족도: Y/X * 1000 단위 보정)
        ratio = (ry / rx) if rx != 0 else 0.0

        region_details.append({
            'region': reg,
            'x': round(rx, 2),
            'y': round(ry, 2),
            'predicted_y': round(float(pred), 2),
            'residual': round(float(res), 2),
            'ratio_yx': round(ratio, 4),
            'quadrant': q_key
        })

    # 회귀 추세선 포인트 (X 최소값~최대값)
    min_x = float(np.min(xs))
    max_x = float(np.max(xs))
    trendline = [
        {'x': round(min_x, 2), 'y': round(beta0 + beta1 * min_x, 2)},
        {'x': round(max_x, 2), 'y': round(beta0 + beta1 * max_x, 2)}
    ]

    return {
        'n': n,
        'df': df_resid,
        'mean_x': round(mean_x, 2),
        'mean_y': round(mean_y, 2),
        'std_x': round(std_x, 2),
        'std_y': round(std_y, 2),
        'pearson_r': round(pearson_r, 4),
        'spearman_rho': round(spearman_rho, 4),
        'beta0': round(beta0, 4),
        'beta1': round(beta1, 4),
        'regression_formula': f"Y = {beta0:.2f} + ({beta1:.2f}) * X",
        'r_squared': round(r_squared, 4),
        'adj_r_squared': round(adj_r_squared, 4),
        't_stat': round(t_stat, 3),
        'p_value': round(p_value, 4),
        'significance': sig_label,
        'is_significant': is_significant,
        'quadrants': quadrants,
        'region_details': region_details,
        'trendline': trendline,
        'excluded_regions': excluded_regions
    }

def generate_analytical_commentary(stats: dict, x_name: str, y_name: str) -> str:
    """통계 원칙을 철저히 반영한 자동 학술 해석 코멘터리 생성"""
    if 'error' in stats:
        return f"[분석 오류] {stats['error']}"

    n = stats['n']
    r = stats['pearson_r']
    r2 = stats['r_squared']
    p = stats['p_value']
    beta1 = stats['beta1']
    sig = stats['significance']

    # 상관 강도
    abs_r = abs(r)
    if abs_r >= 0.7:
        r_desc = "매우 강한"
    elif abs_r >= 0.4:
        r_desc = "중간 정도의"
    elif abs_r >= 0.2:
        r_desc = "약한"
    else:
        r_desc = "거의 무시할 수 있는 수준의"

    dir_desc = "양(+)의 상관관계" if r > 0 else ("음(-)의 상관관계" if r < 0 else "상관 없음")

    lines = [
        f"### 1. 표본수 및 상관분석 요약",
        f"- **분석 대상 표본수(N)**: 17개 광역시도 중 유효 관측치 {n}개",
        f"- **피어슨 상관계수(Pearson r)**: `{r:.4f}` ({r_desc} {dir_desc})",
        f"- **스피어만 순위상관계수(Spearman ρ)**: `{stats['spearman_rho']:.4f}`",
        f"",
        f"### 2. OLS 단순회귀분석 결과",
        f"- **회귀식**: `{stats['regression_formula']}`",
        f"- **결정계수(R²)**: `{r2:.4f}` (X가 Y 변량의 약 {r2*100:.1f}%를 설명)",
        f"- **통계적 유의성(p-value)**: `{p:.4f}` [{sig}]",
    ]

    if not stats['is_significant']:
        lines.append(
            f"> [!WARNING] **통계적 유의성 주의**: p-value({p:.3f})가 유의수준 0.05 이상이므로, "
            f"17개 시도 간의 '{x_name}'과(와) '{y_name}'의 선형적 인과/상관관계가 통계적으로 유의하다고 단정할 수 없습니다."
        )
    else:
        lines.append(
            f"> [!NOTE] 회귀계수(β1={beta1:.2f})에 따르면, '{x_name}'이 1단위 증가할 때 '{y_name}'은(는) "
            f"평균 {abs(beta1):.2f}단위 {'증가' if beta1 > 0 else '감소'}하는 경향이 관찰됩니다."
        )

    # 4분면 추천 해석
    q2_regions = stats['quadrants']['Q2_low_high']['regions']
    q1_regions = stats['quadrants']['Q1_high_high']['regions']
    lines.extend([
        f"",
        f"### 3. 예산 및 가성비 4분면 진단",
        f"- **최고 가성비 권역 (저비용·고만족)**: {', '.join(q2_regions) if q2_regions else '해당 없음'}",
        f"- **프리미엄 만족 권역 (고비용·고만족)**: {', '.join(q1_regions) if q1_regions else '해당 없음'}"
    ])

    return "\n".join(lines)
