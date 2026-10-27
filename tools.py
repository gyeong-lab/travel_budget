# -*- coding: utf-8 -*-
"""
Travel Cost & Satisfaction Insight Builder - Tools Module (tools.py)
12개 통계 분석 도구 구현
원칙: 모든 수치 계산은 Pandas/Numpy가 수행하며, 결과와 함께 기준시점, 사용 행 수, 제외 행 수와 이유를 반환함.
"""
import math
import numpy as np
import pandas as pd

AGGREGATE_KEYWORDS = ['전국', '전체', '소계', '합계', '평균', 'total', 'average', 'all', 'world', 'oecd', 'asia', 'europe']

def safe_number(val):
    """NaN, Infinity 등을 JSON 직렬화 가능한 None 또는 float로 변환"""
    if val is None:
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    return val

def sanitize_dict(d):
    """딕셔너리 내 모든 비안전 부동소수점 변환"""
    if isinstance(d, dict):
        return {k: sanitize_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_dict(v) for v in d]
    else:
        return safe_number(d)

def is_aggregate_row(series):
    """행 내 텍스트에 집계성 키워드가 포함되어 있는지 검사"""
    for item in series:
        if pd.isna(item):
            continue
        text = str(item).strip().lower()
        for kw in AGGREGATE_KEYWORDS:
            if kw in text:
                return True
    return False

def filter_by_period_and_aggregates(df, period_col, ref_period, label_col, exclude_aggr=True):
    """기준 시점 필터링 및 집계 행 제외 처리 헬퍼"""
    df_work = df.copy()
    rows_initial = len(df_work)
    exclusion_log = []

    # 1. 기준 시점 필터링
    if period_col and period_col in df_work.columns and ref_period and str(ref_period).upper() != "ALL":
        match_mask = df_work[period_col].astype(str).str.strip() == str(ref_period).strip()
        non_match = (~match_mask).sum()
        if non_match > 0:
            exclusion_log.append(f"기준 시점({ref_period}) 불일치 {non_match}행 제외")
        df_work = df_work[match_mask]

    # 2. 집계 행 제외
    if exclude_aggr:
        aggr_mask = df_work.apply(is_aggregate_row, axis=1)
        aggr_count = aggr_mask.sum()
        if aggr_count > 0:
            exclusion_log.append(f"집계성 행(전국, 전체, 평균, 합계 등) {aggr_count}행 제외")
        df_work = df_work[~aggr_mask]

    rows_used = len(df_work)
    rows_excluded = rows_initial - rows_used
    return df_work, rows_used, rows_excluded, exclusion_log


# ==========================================
# 도구 1~4: 전처리 및 품질·시점·집계 진단 도구
# ==========================================

def reshape_wide_to_long(df: pd.DataFrame, params: dict) -> dict:
    """1. 연도/시점별 가로 열을 세로 행으로 접기 (pd.melt)"""
    id_vars = params.get('id_vars', [])
    value_vars = params.get('value_vars', [])
    var_name = params.get('var_name', '시점')
    val_name = params.get('value_name', '값')

    # 자동 식별
    if not id_vars:
        id_vars = [c for c in df.columns if df[c].dtype == object][:2]
    if not value_vars:
        value_vars = [c for c in df.columns if c not in id_vars]

    melted = pd.melt(df, id_vars=id_vars, value_vars=value_vars, var_name=var_name, value_name=val_name)
    
    return sanitize_dict({
        "tool": "reshape_wide_to_long",
        "result": {
            "original_shape": list(df.shape),
            "new_shape": list(melted.shape),
            "id_vars": id_vars,
            "value_vars": value_vars,
            "preview": melted.head(10).to_dict(orient='records')
        },
        "reference_period": "전체 변환",
        "rows_used": len(df),
        "rows_excluded": 0,
        "exclusion_reasons": [],
        "columns_used": id_vars + value_vars,
        "unit": "행/열",
        "caution": "연도별 열이 많은 가로형 통계표를 시계열 분석용 세로형으로 재구조화했습니다."
    })

def quality_report(df: pd.DataFrame, params: dict) -> dict:
    """2. 결측·중복·타입·이상한 열 이름 및 극단값(Outlier, IQR 기준) 유무 진단"""
    n_rows, n_cols = df.shape
    dups = int(df.duplicated().sum())

    col_stats = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    outlier_summary = {}
    for c in numeric_cols:
        series = df[c].dropna()
        if len(series) >= 4:
            q25 = series.quantile(0.25)
            q75 = series.quantile(0.75)
            iqr = q75 - q25
            lower_bound = q25 - 1.5 * iqr
            upper_bound = q75 + 1.5 * iqr
            outliers = series[(series < lower_bound) | (series > upper_bound)].tolist()
            if outliers:
                outlier_summary[c] = {
                    "count": len(outliers),
                    "bounds": [round(lower_bound, 2), round(upper_bound, 2)],
                    "samples": [round(x, 2) for x in outliers[:5]]
                }

    for c in df.columns:
        null_cnt = int(df[c].isnull().sum())
        null_ratio = round((null_cnt / n_rows) * 100, 2) if n_rows > 0 else 0
        col_stats.append({
            "column": c,
            "dtype": str(df[c].dtype),
            "null_count": null_cnt,
            "null_ratio_pct": null_ratio,
            "unique_count": int(df[c].nunique())
        })

    return sanitize_dict({
        "tool": "quality_report",
        "result": {
            "total_rows": n_rows,
            "total_cols": n_cols,
            "duplicate_rows": dups,
            "columns": col_stats,
            "outliers_iqr": outlier_summary
        },
        "reference_period": "전체",
        "rows_used": n_rows,
        "rows_excluded": 0,
        "exclusion_reasons": [],
        "columns_used": list(df.columns),
        "unit": "건수, 비율(%)",
        "caution": "IQR 1.5배수 기준 극단값은 오류값일 수도 있고, 관광 특수지(제주, 서울 등)의 정상적인 고비용일 수도 있습니다."
    })

def period_coverage(df: pd.DataFrame, params: dict) -> dict:
    """3. 시점(연도/월)별 값 개수와 권장 기준시점 도출"""
    period_col = params.get('period_column')
    if not period_col or period_col not in df.columns:
        # 시점 열 후보 탐색
        candidates = [c for c in df.columns if any(k in str(c) for k in ['연도', '시점', '년도', 'date', 'year', 'period'])]
        period_col = candidates[0] if candidates else None

    if not period_col:
        return sanitize_dict({
            "tool": "period_coverage",
            "result": {"period_column": None, "coverage": {}, "recommended_period": "ALL"},
            "reference_period": "ALL",
            "rows_used": len(df),
            "rows_excluded": 0,
            "exclusion_reasons": ["시점 열이 감지되지 않아 단일 시점(ALL)으로 처리"],
            "columns_used": [],
            "unit": "시점별 표본수",
            "caution": "시점 구분이 없는 단일 시점 데이터셋입니다."
        })

    counts = df[period_col].astype(str).value_counts().to_dict()
    # 결측치 적고 표본수가 많은 최근 시점 권장
    sorted_periods = sorted(counts.items(), key=lambda x: str(x[0]), reverse=True)
    recommended = sorted_periods[0][0] if sorted_periods else "ALL"

    return sanitize_dict({
        "tool": "period_coverage",
        "result": {
            "period_column": period_col,
            "coverage": counts,
            "recommended_period": recommended
        },
        "reference_period": recommended,
        "rows_used": len(df),
        "rows_excluded": 0,
        "exclusion_reasons": [],
        "columns_used": [period_col],
        "unit": "개",
        "caution": f"시점이 가장 최신이면서 표본이 풍부한 '{recommended}'을(를) 기본 기준시점으로 권장합니다."
    })

def detect_aggregates(df: pd.DataFrame, params: dict) -> dict:
    """4. 집계 행 후보(전국, 전체, 평균, Total 등) 탐지"""
    aggr_rows = []
    for idx, row in df.iterrows():
        if is_aggregate_row(row):
            label = str(row.iloc[0]) if len(row) > 0 else f"Row {idx}"
            aggr_rows.append({"index": idx, "label": label, "sample_values": {str(k): str(v) for k, v in row.dropna().iloc[:3].items()}})

    return sanitize_dict({
        "tool": "detect_aggregates",
        "result": {
            "aggregate_count": len(aggr_rows),
            "aggregate_rows": aggr_rows
        },
        "reference_period": "전체",
        "rows_used": len(df),
        "rows_excluded": 0,
        "exclusion_reasons": [],
        "columns_used": list(df.columns[:2]),
        "unit": "행 수",
        "caution": "집계 행이 포함된 상태로 평균이나 상관계수를 계산하면 통계가 심각하게 왜곡되므로 분석 시 제외해야 합니다."
    })


# ==========================================
# 도구 5~8: 기초통계, 추이, 상하위 N, 구간별 만족도
# ==========================================

def describe_numeric(df: pd.DataFrame, params: dict) -> dict:
    """5. 물가·만족도 등 주요 숫자 열의 개수·평균·중앙값·최소·최대·표준편차·사분위수(IQR)"""
    columns = params.get('columns', [])
    exclude_aggr = params.get('exclude_aggregates', True)

    df_work = df.copy()
    rows_initial = len(df_work)
    if exclude_aggr:
        df_work = df_work[~df_work.apply(is_aggregate_row, axis=1)]

    if not columns:
        columns = df_work.select_dtypes(include=[np.number]).columns.tolist()

    stats = {}
    for c in columns:
        if c in df_work.columns:
            series = pd.to_numeric(df_work[c], errors='coerce').dropna()
            if len(series) > 0:
                q25 = float(series.quantile(0.25))
                q75 = float(series.quantile(0.75))
                stats[c] = {
                    "count": int(len(series)),
                    "mean": float(series.mean()),
                    "std": float(series.std(ddof=1)) if len(series) > 1 else 0.0,
                    "median": float(series.median()),
                    "min": float(series.min()),
                    "max": float(series.max()),
                    "q25": q25,
                    "q75": q75,
                    "iqr": float(q75 - q25)
                }

    return sanitize_dict({
        "tool": "describe_numeric",
        "result": stats,
        "reference_period": "전체",
        "rows_used": len(df_work),
        "rows_excluded": rows_initial - len(df_work),
        "exclusion_reasons": ["집계 행 제외"] if exclude_aggr else [],
        "columns_used": columns,
        "unit": "지표별 단위",
        "caution": "왜도가 큰 지표(일부 초고가 관광지)의 경우 평균보다 중앙값(Median)이 대표값으로 더 적합합니다."
    })

def trend_line(df: pd.DataFrame, params: dict) -> dict:
    """6. 선택 여행지들의 시점별 물가 또는 만족도 추이 (선 차트)"""
    period_col = params.get('period_column')
    label_col = params.get('label_column')
    value_col = params.get('value_column')
    target_places = params.get('places', [])

    if not (period_col in df.columns and label_col in df.columns and value_col in df.columns):
        raise ValueError("period_column, label_column, value_column이 올바르지 않습니다.")

    df_clean = df.copy()
    df_clean[value_col] = pd.to_numeric(df_clean[value_col], errors='coerce')
    df_clean = df_clean.dropna(subset=[value_col, period_col, label_col])

    if target_places:
        df_clean = df_clean[df_clean[label_col].isin(target_places)]

    # 피벗 테이블 생성
    pivot = df_clean.pivot_table(index=period_col, columns=label_col, values=value_col, aggfunc='mean')
    periods = [str(p) for p in pivot.index]

    series_data = []
    for place in pivot.columns:
        series_data.append({
            "label": str(place),
            "values": [safe_number(v) for v in pivot[place].tolist()]
        })

    return sanitize_dict({
        "tool": "trend_line",
        "result": {
            "periods": periods,
            "series": series_data
        },
        "chart": {
            "type": "line",
            "x_axis": periods,
            "datasets": series_data
        },
        "reference_period": f"{periods[0]} ~ {periods[-1]}" if periods else "ALL",
        "rows_used": len(df_clean),
        "rows_excluded": len(df) - len(df_clean),
        "exclusion_reasons": ["결측치 및 미선택 여행지 제외"],
        "columns_used": [period_col, label_col, value_col],
        "unit": "시점별 수치",
        "caution": "시계열 변동 추세에서 결측이 있는 연도는 선이 단절될 수 있습니다."
    })

def top_bottom_n(df: pd.DataFrame, params: dict) -> dict:
    """7. 기준시점 기준 특정 지표(물가 또는 만족도) 상위·하위 N개 여행지 (수평 막대)"""
    ref_period = params.get('reference_period')
    period_col = params.get('period_column')
    label_col = params.get('label_column')
    value_col = params.get('value_column')
    n = int(params.get('n', 5))
    exclude_aggr = params.get('exclude_aggregates', True)

    if not ref_period:
        raise ValueError("7번 도구는 reference_period(기준시점) 파라미터가 필수입니다.")

    df_work, r_used, r_excl, ex_log = filter_by_period_and_aggregates(df, period_col, ref_period, label_col, exclude_aggr)
    df_work[value_col] = pd.to_numeric(df_work[value_col], errors='coerce')
    
    # NaN 제외
    valid_mask = df_work[value_col].notnull()
    nan_count = (~valid_mask).sum()
    if nan_count > 0:
        ex_log.append(f"{value_col} 결측치 {nan_count}행 제외")
    df_work = df_work[valid_mask]

    sorted_df = df_work.sort_values(by=value_col, ascending=False)
    top_n = sorted_df.head(n)[[label_col, value_col]].to_dict(orient='records')
    bottom_n = sorted_df.tail(n).sort_values(by=value_col, ascending=True)[[label_col, value_col]].to_dict(orient='records')

    return sanitize_dict({
        "tool": "top_bottom_n",
        "result": {
            "top_n": top_n,
            "bottom_n": bottom_n,
            "metric": value_col,
            "n": n
        },
        "chart": {
            "type": "horizontal_bar",
            "top_labels": [d[label_col] for d in top_n],
            "top_values": [d[value_col] for d in top_n],
            "bottom_labels": [d[label_col] for d in bottom_n],
            "bottom_values": [d[value_col] for d in bottom_n]
        },
        "reference_period": ref_period,
        "rows_used": len(df_work),
        "rows_excluded": len(df) - len(df_work),
        "exclusion_reasons": ex_log,
        "columns_used": [c for c in [label_col, value_col, period_col] if c],
        "unit": "수치",
        "caution": f"기준시점({ref_period})에서 유효한 관측치만 랭킹에 반영되었습니다."
    })

def cost_bracket_satisfaction(df: pd.DataFrame, params: dict) -> dict:
    """8. 물가 구간(저물가·중물가·고물가 3분위 등)별 평균 만족도 비교 (막대 차트)"""
    ref_period = params.get('reference_period')
    period_col = params.get('period_column')
    label_col = params.get('label_column')
    cost_col = params.get('cost_column')
    sat_col = params.get('satisfaction_column')
    num_brackets = int(params.get('brackets', 3))
    exclude_aggr = params.get('exclude_aggregates', True)

    if not ref_period:
        raise ValueError("8번 도구는 reference_period(기준시점) 파라미터가 필수입니다.")

    df_work, _, _, ex_log = filter_by_period_and_aggregates(df, period_col, ref_period, label_col, exclude_aggr)
    df_work[cost_col] = pd.to_numeric(df_work[cost_col], errors='coerce')
    df_work[sat_col] = pd.to_numeric(df_work[sat_col], errors='coerce')

    valid_mask = df_work[cost_col].notnull() & df_work[sat_col].notnull()
    nan_count = (~valid_mask).sum()
    if nan_count > 0:
        ex_log.append(f"물가 또는 만족도 결측치 {nan_count}행 제외")
    df_work = df_work[valid_mask]

    if len(df_work) < num_brackets:
        raise ValueError(f"유효 관측치(N={len(df_work)})가 구간 수({num_brackets})보다 적어 분위수를 나눌 수 없습니다.")

    # 분위수 구간 분할
    labels = ['저비용(하위)', '중간비용', '고비용(상위)'] if num_brackets == 3 else [f"{i+1}분위" for i in range(num_brackets)]
    df_work['bracket'] = pd.qcut(df_work[cost_col], q=num_brackets, labels=labels, duplicates='drop')

    bracket_summary = []
    for grp_name, group in df_work.groupby('bracket', observed=True):
        bracket_summary.append({
            "bracket": str(grp_name),
            "count": int(len(group)),
            "cost_range": [round(group[cost_col].min(), 2), round(group[cost_col].max(), 2)],
            "cost_mean": round(group[cost_col].mean(), 2),
            "satisfaction_mean": round(group[sat_col].mean(), 2),
            "satisfaction_median": round(group[sat_col].median(), 2),
            "places": group[label_col].tolist() if label_col in group.columns else []
        })

    return sanitize_dict({
        "tool": "cost_bracket_satisfaction",
        "result": bracket_summary,
        "chart": {
            "type": "bar",
            "labels": [b["bracket"] for b in bracket_summary],
            "values": [b["satisfaction_mean"] for b in bracket_summary]
        },
        "reference_period": ref_period,
        "rows_used": len(df_work),
        "rows_excluded": len(df) - len(df_work),
        "exclusion_reasons": ex_log,
        "columns_used": [c for c in [cost_col, sat_col, label_col, period_col] if c],
        "unit": "평균 만족도 점수",
        "caution": "물가 구간별 단순 평균 비교이며, 각 구간 내 여행지별 자연경관·인프라 등 다른 변수가 통제되지 않았습니다."
    })


# ==========================================
# 도구 9~12: 가성비 순위, 분포, 상관분석·4사분면, 1대 전체 비교
# ==========================================

def value_for_money_rank(df: pd.DataFrame, params: dict) -> dict:
    """9. 가성비 지수(만족도 ÷ 물가 정규화 비율) 상위·하위 여행지 도출 (수평 막대)"""
    ref_period = params.get('reference_period')
    period_col = params.get('period_column')
    label_col = params.get('label_column')
    cost_col = params.get('cost_column')
    sat_col = params.get('satisfaction_column')
    n = int(params.get('n', 5))
    exclude_aggr = params.get('exclude_aggregates', True)

    if not ref_period:
        raise ValueError("9번 도구는 reference_period(기준시점) 파라미터가 필수입니다.")

    df_work, _, _, ex_log = filter_by_period_and_aggregates(df, period_col, ref_period, label_col, exclude_aggr)
    df_work[cost_col] = pd.to_numeric(df_work[cost_col], errors='coerce')
    df_work[sat_col] = pd.to_numeric(df_work[sat_col], errors='coerce')

    valid_mask = df_work[cost_col].notnull() & df_work[sat_col].notnull() & (df_work[cost_col] > 0)
    df_work = df_work[valid_mask]

    # 가성비 지수 = (만족도 / 평균만족도) / (비용 / 평균비용)
    mean_sat = df_work[sat_col].mean()
    mean_cost = df_work[cost_col].mean()
    df_work['vfm_index'] = (df_work[sat_col] / mean_sat) / (df_work[cost_col] / mean_cost)

    sorted_df = df_work.sort_values(by='vfm_index', ascending=False)
    top_vfm = sorted_df.head(n)[[label_col, cost_col, sat_col, 'vfm_index']].to_dict(orient='records')
    bottom_vfm = sorted_df.tail(n).sort_values(by='vfm_index', ascending=True)[[label_col, cost_col, sat_col, 'vfm_index']].to_dict(orient='records')

    return sanitize_dict({
        "tool": "value_for_money_rank",
        "result": {
            "top_vfm": top_vfm,
            "bottom_vfm": bottom_vfm,
            "mean_benchmark": {"mean_cost": round(mean_cost, 2), "mean_satisfaction": round(mean_sat, 2)}
        },
        "chart": {
            "type": "horizontal_bar",
            "top_labels": [d[label_col] for d in top_vfm],
            "top_values": [round(d['vfm_index'], 3) for d in top_vfm]
        },
        "reference_period": ref_period,
        "rows_used": len(df_work),
        "rows_excluded": len(df) - len(df_work),
        "exclusion_reasons": ex_log,
        "columns_used": [c for c in [cost_col, sat_col, label_col, period_col] if c],
        "unit": "가성비 지수(1.0=전국평균 대비 효율)",
        "caution": "지수가 1.0보다 크면 평균 대비 적은 비용으로 높은 만족도를 달성한 가성비 우수 지역입니다."
    })

def distribution(df: pd.DataFrame, params: dict) -> dict:
    """10. 물가 또는 만족도 점수의 구간별 분포와 왜도 확인 (히스토그램)"""
    ref_period = params.get('reference_period')
    period_col = params.get('period_column')
    value_col = params.get('value_column')
    bins = int(params.get('bins', 5))
    exclude_aggr = params.get('exclude_aggregates', True)

    if not ref_period:
        raise ValueError("10번 도구는 reference_period(기준시점) 파라미터가 필수입니다.")

    df_work, _, _, ex_log = filter_by_period_and_aggregates(df, period_col, ref_period, None, exclude_aggr)
    series = pd.to_numeric(df_work[value_col], errors='coerce').dropna()

    if len(series) < 3:
        raise ValueError("분포 분석을 위해 최소 3개 이상의 수치 데이터가 필요합니다.")

    counts, bin_edges = np.histogram(series, bins=bins)
    bin_labels = [f"{round(bin_edges[i], 1)}~{round(bin_edges[i+1], 1)}" for i in range(len(counts))]
    skewness = float(series.skew())

    return sanitize_dict({
        "tool": "distribution",
        "result": {
            "column": value_col,
            "bins": bin_labels,
            "frequencies": [int(c) for c in counts],
            "skewness": round(skewness, 3),
            "distribution_shape": "우측 꼬리형(일부 초고가)" if skewness > 0.5 else ("좌측 꼬리형" if skewness < -0.5 else "대칭에 가까움")
        },
        "chart": {
            "type": "bar",
            "labels": bin_labels,
            "values": [int(c) for c in counts]
        },
        "reference_period": ref_period,
        "rows_used": len(series),
        "rows_excluded": len(df) - len(series),
        "exclusion_reasons": ex_log,
        "columns_used": [value_col],
        "unit": "빈도(지역 개수)",
        "caution": "왜도가 심하게 치우친 경우 특정 극단치 지역(Outlier)이 통계에 영향을 미치고 있음을 의미합니다."
    })

def correlation_scatter(df: pd.DataFrame, params: dict) -> dict:
    """11. 물가 열(X축)과 만족도 열(Y축)의 피어슨 상관계수(r), 결정계수(R²), 4사분면 분류 (산점도)"""
    ref_period = params.get('reference_period')
    period_col = params.get('period_column')
    label_col = params.get('label_column')
    x_col = params.get('x_column')
    y_col = params.get('y_column')
    exclude_aggr = params.get('exclude_aggregates', True)

    if not ref_period:
        raise ValueError("11번 도구는 reference_period(기준시점) 파라미터가 필수입니다.")

    df_work, _, _, ex_log = filter_by_period_and_aggregates(df, period_col, ref_period, label_col, exclude_aggr)
    df_work[x_col] = pd.to_numeric(df_work[x_col], errors='coerce')
    df_work[y_col] = pd.to_numeric(df_work[y_col], errors='coerce')

    valid_mask = df_work[x_col].notnull() & df_work[y_col].notnull()
    nan_count = (~valid_mask).sum()
    if nan_count > 0:
        ex_log.append(f"X축 또는 Y축 결측치 {nan_count}행 제외")
    df_work = df_work[valid_mask]

    n = len(df_work)
    if n < 3:
        raise ValueError(f"상관계수 계산에 필요한 유효 관측치(N={n})가 부족합니다 (최소 3개 이상 필요).")

    xs = df_work[x_col].values
    ys = df_work[y_col].values
    mean_x = float(np.mean(xs))
    mean_y = float(np.mean(ys))
    std_x = float(np.std(xs, ddof=1))
    std_y = float(np.std(ys, ddof=1))

    # Pearson r
    cov_xy = float(np.cov(xs, ys, ddof=1)[0][1])
    r = cov_xy / (std_x * std_y) if std_x > 0 and std_y > 0 else 0.0
    r2 = r ** 2

    # OLS 회귀선
    beta1 = cov_xy / (std_x ** 2) if std_x > 0 else 0.0
    beta0 = mean_y - beta1 * mean_x

    # r 강도 해석
    abs_r = abs(r)
    strength = "강한 상관관계 (|r| > 0.7)" if abs_r > 0.7 else ("보통의 상관관계 (0.3 ≤ |r| ≤ 0.7)" if abs_r >= 0.3 else "약하거나 무시할 수준 (|r| < 0.3)")
    direction = "양(+)의 방향" if r > 0 else ("음(-)의 방향" if r < 0 else "상관 없음")

    # 4사분면 분류
    quadrants = {
        "Q1_premium": {"name": "1사분면(고물가·고만족: 프리미엄)", "places": []},
        "Q2_value": {"name": "2사분면(저물가·고만족: 가성비 추천)", "places": []},
        "Q3_budget": {"name": "3사분면(저물가·저만족: 알뜰실속)", "places": []},
        "Q4_caution": {"name": "4사분면(고물가·저만족: 바가지 주의)", "places": []}
    }

    points = []
    for _, row in df_work.iterrows():
        px = float(row[x_col])
        py = float(row[y_col])
        pname = str(row[label_col]) if label_col in row else "지점"
        
        if px >= mean_x and py >= mean_y:
            q_key = "Q1_premium"
        elif px < mean_x and py >= mean_y:
            q_key = "Q2_value"
        elif px < mean_x and py < mean_y:
            q_key = "Q3_budget"
        else:
            q_key = "Q4_caution"

        quadrants[q_key]["places"].append(pname)
        points.append({"label": pname, "x": round(px, 2), "y": round(py, 2), "quadrant": q_key})

    # 회귀 추세선
    min_x, max_x = float(np.min(xs)), float(np.max(xs))
    trendline = [
        {"x": round(min_x, 2), "y": round(beta0 + beta1 * min_x, 2)},
        {"x": round(max_x, 2), "y": round(beta0 + beta1 * max_x, 2)}
    ]

    return sanitize_dict({
        "tool": "correlation_scatter",
        "result": {
            "n": n,
            "pearson_r": round(r, 4),
            "r_squared": round(r2, 4),
            "strength": strength,
            "direction": direction,
            "regression_formula": f"Y = {beta0:.2f} + ({beta1:.2f}) * X",
            "mean_x": round(mean_x, 2),
            "mean_y": round(mean_y, 2),
            "quadrants": quadrants,
            "points": points,
            "trendline": trendline
        },
        "chart": {
            "type": "scatter",
            "points": points,
            "trendline": trendline,
            "split_x": round(mean_x, 2),
            "split_y": round(mean_y, 2)
        },
        "reference_period": ref_period,
        "rows_used": n,
        "rows_excluded": len(df) - n,
        "exclusion_reasons": ex_log,
        "columns_used": [x_col, y_col, label_col],
        "unit": f"X: {x_col}, Y: {y_col}",
        "caution": "⚠️ 상관관계는 인과관계가 아닙니다. 물가가 높아 만족도가 올랐다고 단정할 수 없으며, 인프라나 자연경관 등 제3의 교락 변수가 개입되었을 수 있습니다."
    })

def compare_one_vs_all(df: pd.DataFrame, params: dict) -> dict:
    """12. 특정 여행지의 물가·만족도 vs 전체 평균·중앙값 비교 (강조 막대)"""
    ref_period = params.get('reference_period')
    period_col = params.get('period_column')
    label_col = params.get('label_column')
    value_col = params.get('value_column')
    target_place = params.get('place')
    exclude_aggr = params.get('exclude_aggregates', True)

    if not ref_period:
        raise ValueError("12번 도구는 reference_period(기준시점) 파라미터가 필수입니다.")
    if not target_place:
        raise ValueError("비교 대상 여행지(place)를 지정해야 합니다.")

    df_work, _, _, ex_log = filter_by_period_and_aggregates(df, period_col, ref_period, label_col, exclude_aggr)
    df_work[value_col] = pd.to_numeric(df_work[value_col], errors='coerce')
    df_work = df_work.dropna(subset=[value_col])

    target_row = df_work[df_work[label_col].astype(str) == str(target_place)]
    if len(target_row) == 0:
        raise ValueError(f"기준시점({ref_period})에 '{target_place}' 데이터가 존재하지 않습니다.")

    target_val = float(target_row[value_col].iloc[0])
    all_mean = float(df_work[value_col].mean())
    all_median = float(df_work[value_col].median())
    diff_from_mean = target_val - all_mean

    rank = int((df_work[value_col] > target_val).sum() + 1)
    total_places = len(df_work)

    return sanitize_dict({
        "tool": "compare_one_vs_all",
        "result": {
            "place": target_place,
            "target_value": round(target_val, 2),
            "benchmark_mean": round(all_mean, 2),
            "benchmark_median": round(all_median, 2),
            "diff_from_mean": round(diff_from_mean, 2),
            "rank": rank,
            "total_places": total_places
        },
        "chart": {
            "type": "bar",
            "labels": [str(target_place), "전국 평균", "전국 중앙값"],
            "values": [round(target_val, 2), round(all_mean, 2), round(all_median, 2)]
        },
        "reference_period": ref_period,
        "rows_used": total_places,
        "rows_excluded": len(df) - total_places,
        "exclusion_reasons": ex_log,
        "columns_used": [value_col, label_col],
        "unit": "수치",
        "caution": f"'{target_place}'의 지표가 전체 {total_places}개 지역 중 {rank}위입니다."
    })


# 도구 매핑 카탈로그
TOOL_CATALOG = {
    "reshape_wide_to_long": reshape_wide_to_long,
    "quality_report": quality_report,
    "period_coverage": period_coverage,
    "detect_aggregates": detect_aggregates,
    "describe_numeric": describe_numeric,
    "trend_line": trend_line,
    "top_bottom_n": top_bottom_n,
    "cost_bracket_satisfaction": cost_bracket_satisfaction,
    "value_for_money_rank": value_for_money_rank,
    "distribution": distribution,
    "correlation_scatter": correlation_scatter,
    "compare_one_vs_all": compare_one_vs_all
}
