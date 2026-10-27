# -*- coding: utf-8 -*-
"""
Korea Travel Insight Engine
국내 여행지별 지출액 및 만족도 상관분석·회귀분석·4분면 통계 엔진
"""
import io
import math
import numpy as np
import pandas as pd

STANDARD_REGIONS = [
    '서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종',
    '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'
]

def calculate_student_t_pvalue(t_val: float, df: int) -> float:
    """2-tailed Student's t-distribution p-value 수치 적분 계산"""
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
    """인코딩 자동 판별"""
    for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
        try:
            return content_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return content_bytes.decode('cp949', errors='ignore')

def parse_kosis_csv(content_bytes: bytes, filename: str):
    """
    KOSIS 및 국민여행조사 CSV 파싱:
    - 2단 멀티헤더 (시점, 17개 광역시도) 자동 감지
    - 품목별 지출 비중 등 비지역 통계 분리
    """
    text = detect_encoding_and_read(content_bytes)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("빈 파일입니다.")

    second_line = lines[1] if len(lines) > 1 else ""
    is_regional_2level = any(r in second_line for r in STANDARD_REGIONS)

    if is_regional_2level:
        df = pd.read_csv(io.StringIO(text), header=[0, 1])
        c0 = [str(col[0]).strip() for col in df.columns]
        c1 = [str(col[1]).strip() for col in df.columns]

        cat1_idx = 0
        cat2_idx = 1
        for i, (name0, name1) in enumerate(zip(c0, c1)):
            if '통계분류(1)' in name0 or '통계분류(1)' in name1:
                cat1_idx = i
            elif '통계분류(2)' in name0 or '통계분류(2)' in name1:
                cat2_idx = i

        region_cols = {}
        for i, name1 in enumerate(c1):
            for reg in STANDARD_REGIONS:
                if reg == name1:
                    region_cols[reg] = df.columns[i]
                    break

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
                val_str = str(row[col]).replace(',', '').strip()
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

    # 단일 헤더 또는 비지역 통계
    df_single = pd.read_csv(io.StringIO(text))
    col_names = [str(c).strip() for c in df_single.columns]
    
    reg_col = None
    for c in col_names:
        sample_vals = df_single[c].dropna().astype(str).tolist()[:10]
        if any(r in sample_vals for r in STANDARD_REGIONS):
            reg_col = c
            break

    if reg_col:
        numeric_cols = [c for c in col_names if c != reg_col and pd.to_numeric(df_single[c], errors='coerce').notnull().sum() > 3]
        records = []
        for num_col in numeric_cols:
            val_map = {}
            for _, row in df_single.iterrows():
                r_name = str(row[reg_col]).strip()
                matched_reg = next((std_r for std_r in STANDARD_REGIONS if std_r in r_name), None)
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
            'regions': STANDARD_REGIONS
        }

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
    17개 시도 실측치 기반 상관분석 및 OLS 선형회귀
    없는 수치는 일절 생성하지 않고 결측치 제외 개수와 이유 명시
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
            'error': f'유효 관측치(N={n})가 부족합니다.',
            'n': n,
            'excluded_regions': excluded_regions
        }

    xs = np.array([p['x'] for p in paired_data], dtype=float)
    ys = np.array([p['y'] for p in paired_data], dtype=float)

    mean_x = float(np.mean(xs))
    mean_y = float(np.mean(ys))
    std_x = float(np.std(xs, ddof=1)) if n > 1 else 0.0
    std_y = float(np.std(ys, ddof=1)) if n > 1 else 0.0

    cov_xy = float(np.cov(xs, ys, ddof=1)[0][1]) if n > 1 else 0.0
    pearson_r = (cov_xy / (std_x * std_y)) if (std_x > 0 and std_y > 0) else 0.0

    rank_x = pd.Series(xs).rank().values
    rank_y = pd.Series(ys).rank().values
    spearman_rho = float(np.cov(rank_x, rank_y, ddof=1)[0][1] / (np.std(rank_x, ddof=1) * np.std(rank_y, ddof=1))) if (np.std(rank_x, ddof=1) > 0 and np.std(rank_y, ddof=1) > 0) else 0.0

    df_resid = n - 2
    beta1 = (cov_xy / (std_x ** 2)) if std_x > 0 else 0.0
    beta0 = mean_y - beta1 * mean_x

    y_pred = beta0 + beta1 * xs
    residuals = ys - y_pred
    ss_tot = float(np.sum((ys - mean_y) ** 2))
    ss_res = float(np.sum(residuals ** 2))

    r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
    adj_r_squared = float(1.0 - ((ss_res / df_resid) / (ss_tot / (n - 1)))) if df_resid > 0 and ss_tot > 0 else 0.0

    se_resid = math.sqrt(ss_res / df_resid) if df_resid > 0 else 0.0
    sum_x_dev_sq = float(np.sum((xs - mean_x) ** 2))
    se_beta1 = (se_resid / math.sqrt(sum_x_dev_sq)) if sum_x_dev_sq > 0 else 0.0

    t_stat = (beta1 / se_beta1) if se_beta1 > 0 else 0.0
    p_value = calculate_student_t_pvalue(t_stat, df_resid)

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
        
        if rx >= mean_x and ry >= mean_y:
            q_key = 'Q1_high_high'
        elif rx < mean_x and ry >= mean_y:
            q_key = 'Q2_low_high'
        elif rx < mean_x and ry < mean_y:
            q_key = 'Q3_low_low'
        else:
            q_key = 'Q4_high_low'

        quadrants[q_key]['regions'].append(reg)
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
