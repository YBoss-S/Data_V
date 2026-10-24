"""ทดสอบฟังก์ชันคำนวณใน data_loader.py และ charts.py

DataFrame ในไฟล์นี้เป็นข้อมูลทดสอบขนาดเล็กสำหรับ unit test เท่านั้น ไม่ใช่ข้อมูลของ Dashboard
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import charts  # noqa: E402
import data_loader as dl  # noqa: E402


def make_students(rows: list[tuple]) -> pd.DataFrame:
    """rows: (GPA, Extracurricular)"""
    n = len(rows)
    return pd.DataFrame({
        "StudentID": range(n), "GPA": [r[0] for r in rows],
        "Extracurricular": [r[1] for r in rows], "Sports": [0] * n, "Music": [0] * n,
        "Volunteering": [0] * n, "Absences": [1] * n, "StudyTimeWeekly": [5.0] * n,
    })


# ---------- โหลดไฟล์ ----------
def test_missing_file_message_names_file_and_path(tmp_path):
    with pytest.raises(dl.DataLoadError) as exc:
        dl.read_csv_checked(tmp_path / "nope.csv", ["GPA"])
    assert "nope.csv" in exc.value.message and str(tmp_path) in exc.value.message


def test_missing_column_is_named(tmp_path):
    path = tmp_path / "a.csv"
    pd.DataFrame({"GPA": [1.0]}).to_csv(path, index=False)
    with pytest.raises(dl.DataLoadError) as exc:
        dl.read_csv_checked(path, ["GPA", "Extracurricular"])
    assert "Extracurricular" in exc.value.message and "GPA," not in exc.value.message


def test_empty_file_gives_friendly_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(dl.DataLoadError):
        dl.read_csv_checked(path, ["GPA"])


# ---------- ตรวจสอบข้อมูลนิสิต ----------
def test_prepare_students_keeps_valid_rows_and_reports_nothing():
    result = dl.prepare_students(make_students([(3.0, 1), (2.0, 0)]))
    assert len(result.df) == 2 and result.notes == []


def test_prepare_students_drops_invalid_rows_with_notes():
    raw = make_students([(3.0, 1), (5.0, 0), (np.nan, 1), (2.0, 2), (1.0, 0)])
    result = dl.prepare_students(raw)
    assert list(result.df["GPA"]) == [3.0, 1.0]
    assert len(result.notes) == 3  # ว่าง, นอกช่วง, ไม่ใช่ 0/1
    assert result.rows_loaded == 5


def test_prepare_students_does_not_mutate_input():
    raw = make_students([(3.0, 1), (9.0, 0)])
    snapshot = raw.copy()
    dl.prepare_students(raw)
    pd.testing.assert_frame_equal(raw, snapshot)


# ---------- ตัวกรอง ----------
def test_filter_by_gpa_range_is_inclusive_and_returns_copy():
    df = make_students([(1.0, 0), (2.0, 1), (3.0, 1), (4.0, 0)])
    out = dl.filter_students(df, (2.0, 3.0))
    assert list(out["GPA"]) == [2.0, 3.0]
    out.loc[:, "GPA"] = 0
    assert df["GPA"].max() == 4.0  # ต้นฉบับไม่เปลี่ยน


@pytest.mark.parametrize("activity,expected", [("all", 4), ("participant", 2), ("non_participant", 2)])
def test_filter_by_activity(activity, expected):
    df = make_students([(1.0, 0), (2.0, 1), (3.0, 1), (4.0, 0)])
    assert len(dl.filter_students(df, (0, 4), activity)) == expected


def test_filter_rejects_unknown_activity():
    with pytest.raises(ValueError):
        dl.filter_students(make_students([(1.0, 0)]), (0, 4), "bogus")


def test_filter_swapped_range_and_empty_result():
    df = make_students([(1.0, 0), (2.0, 1)])
    assert len(dl.filter_students(df, (2.0, 1.0))) == 2
    assert dl.filter_students(df, (3.0, 3.5)).empty


def test_normalise_gpa_range_clamps_and_sorts():
    assert dl.normalise_gpa_range((5.0, -1.0), 0.0, 4.0) == (0.0, 4.0)


def test_slider_bounds_come_from_data():
    assert dl.gpa_slider_bounds(make_students([(0.62, 0), (3.41, 1)])) == (0.6, 3.5)
    assert dl.gpa_slider_bounds(make_students([])) == (0.0, 4.0)


# ---------- KPI / สถิติ ----------
def test_kpis_values_and_empty_case():
    kpi = dl.student_kpis(make_students([(2.0, 1), (4.0, 0), (3.0, 1), (3.0, 0)]))
    assert kpi["n"] == 4 and kpi["n_active"] == 2
    assert kpi["mean_gpa"] == pytest.approx(3.0) and kpi["pct_active"] == pytest.approx(50.0)
    empty = dl.student_kpis(make_students([]))
    assert empty["n"] == 0 and empty["mean_gpa"] is None and empty["pct_active"] is None


def test_group_summary_has_both_groups_even_if_one_empty():
    out = dl.group_summary(make_students([(2.0, 1), (3.0, 1)]))
    assert list(out.index) == [0, 1]
    assert out.loc[0, "count"] == 0 and math.isnan(out.loc[0, "mean"])
    assert out.loc[1, "mean"] == pytest.approx(2.5)


def test_mean_difference_known_values():
    rng = np.random.default_rng(0)
    with_flag = rng.normal(3.0, 0.5, 200)
    without = rng.normal(2.0, 0.5, 200)
    rows = [(g, 1) for g in with_flag] + [(g, 0) for g in without]
    result = dl.mean_difference(make_students(rows))
    assert result.diff == pytest.approx(with_flag.mean() - without.mean())
    assert result.ci_low < result.diff < result.ci_high and result.ci_excludes_zero
    se = math.sqrt(with_flag.var(ddof=1) / 200 + without.var(ddof=1) / 200)
    assert result.ci_high - result.diff == pytest.approx(1.96 * se)


def test_mean_difference_needs_enough_samples():
    rows = [(2.0, 1)] * 10 + [(3.0, 0)] * 100
    assert dl.mean_difference(make_students(rows)) is None
    assert dl.mean_difference(make_students([])) is None


def test_mean_difference_zero_variance_does_not_crash():
    rows = [(2.0, 1)] * 40 + [(2.0, 0)] * 40
    result = dl.mean_difference(make_students(rows))
    assert result.diff == 0 and result.cohens_d is None


def test_safe_correlation_edge_cases():
    df = make_students([(1.0, 0), (2.0, 1), (3.0, 0)])
    df["Absences"] = [3, 2, 1]
    assert dl.safe_correlation(df, "GPA", "Absences") == pytest.approx(-1.0)
    assert dl.safe_correlation(make_students([(1.0, 0)]), "GPA", "Absences") is None
    df["Absences"] = 5
    assert dl.safe_correlation(df, "GPA", "Absences") is None


def test_activity_table_skips_empty_groups():
    table = dl.activity_gpa_table(make_students([(2.0, 1), (3.0, 1)]))
    ext = table[table["activity"].str.contains("Extracurricular")]
    assert list(ext["group"]) == ["เข้าร่วม"]


# ---------- ข้อมูลประกาศงาน ----------
def make_jobs() -> pd.DataFrame:
    return pd.DataFrame({
        "job_title": ["a", "b", "c", "a"], "company": ["x", "y", "z", "x"],
        "location": ["India", "Pune", None, "India"], "category": ["IT Jobs"] * 4,
        "created_date": ["2025-01-01 10:00:00+00:00", "2025-03-01 10:00:00+00:00", "bad", "2025-01-01 10:00:00+00:00"],
        "description": ["Strong teamwork and Python", "Steam engine; communication", None, "Strong teamwork and Python"],
        "skills": ["SQL, python , sql", "python", None, "SQL, python , sql"],
    })


def test_skill_counts_are_per_posting_and_normalised():
    counts = dl.count_listed_skills(make_jobs()).set_index("skill")["postings"]
    assert counts["sql"] == 2      # "sql" ซ้ำในประกาศเดียวนับครั้งเดียว
    assert counts["python"] == 3


def test_soft_keywords_use_word_boundaries():
    soft = dl.count_soft_skill_keywords(make_jobs()).set_index("skill")["postings"]
    team = soft[[s for s in soft.index if "Team" in s][0]]
    assert team == 2               # "Steam" ต้องไม่ถูกนับ, teamwork 2 ประกาศ (รวมแถวซ้ำ)
    assert soft[[s for s in soft.index if "Communication" in s][0]] == 1


def test_job_bundle_profile():
    bundle = dl.build_job_bundle(make_jobs())
    assert bundle.n_postings == 4 and bundle.n_with_skills == 3 and bundle.n_duplicates == 1
    assert (bundle.date_min, bundle.date_max) == ("2025-01-01", "2025-03-01")


def test_with_percentage_zero_denominator():
    out = dl.with_percentage(pd.DataFrame({"skill": ["a"], "postings": [3]}), 0)
    assert math.isnan(out.loc[0, "pct"])


# ---------- Benchmark ----------
def test_perception_gap_formula_and_order():
    gap = dl.get_perception_benchmark()
    assert (gap["gap"] == (gap["student_score"] - gap["industry_score"]).round(2)).all()
    assert gap["gap"].is_monotonic_increasing and gap.loc[0, "gap"] == pytest.approx(-1.7)


def test_progression_order_and_changes():
    long = dl.get_progression_benchmark()
    assert list(long["phase"].cat.categories) == dl.PHASES
    changes = dl.progression_changes(long).set_index("skill")
    assert changes.loc["การทำงานกลุ่ม (Groupwork)", "เปลี่ยน Phase 1→2"] == pytest.approx(1.3)


# ---------- กราฟ (smoke test ครอบคลุมกรณีขอบ) ----------
def test_charts_build_with_normal_and_edge_data():
    df = make_students([(1.0, 0), (2.0, 1), (3.0, 1)])
    one_group = make_students([(2.0, 1)])
    for data in (df, one_group, make_students([])):
        assert charts.gpa_box_chart(data) is not None
        assert charts.gpa_histogram_chart(data) is not None
        assert charts.activity_gpa_chart(dl.activity_gpa_table(data)) is not None
    assert charts.perception_gap_chart(dl.get_perception_benchmark()) is not None
    long = dl.get_progression_benchmark()
    assert len(charts.progression_chart(long, list(long["skill"].unique())).data) == 3
    demand = dl.with_percentage(dl.count_listed_skills(make_jobs()), 4).assign(label=lambda d: d["skill"])
    assert charts.skill_demand_chart(demand, "t", "x") is not None


# ---------- ไฟล์ข้อมูลจริงในโปรเจกต์ ----------
@pytest.mark.skipif(not dl.STUDENT_FILE.is_file() or not dl.JOB_FILE.is_file(), reason="ไม่มีไฟล์ใน data/")
def test_real_datasets_load_and_match_audit():
    students = dl.load_student_data()
    assert len(students.df) == 2392 and students.notes == []
    jobs = dl.load_job_bundle()
    assert jobs.n_postings == 1000 and jobs.n_with_skills == 406
    top = jobs.skill_counts.iloc[0]
    assert (top["skill"], top["postings"]) == ("sql", 194)
