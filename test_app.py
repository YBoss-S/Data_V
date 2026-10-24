"""ทดสอบการทำงานของแอปด้วย streamlit.testing.v1.AppTest (รันสคริปต์จริงโดยไม่เปิดเบราว์เซอร์)

ไม่ครอบคลุม: การแสดงผลจริงในเบราว์เซอร์, Responsive layout, การใช้งานด้วย Keyboard
"""
import shutil
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import data_loader as dl  # noqa: E402

APP = str(ROOT / "app.py")
TIMEOUT = 60


def run_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    return at


def metric_values(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_app_runs_without_exception():
    at = run_app()
    assert not at.exception
    assert not at.error


def test_kpis_match_source_data():
    at = run_app()
    students = dl.load_student_data().df
    values = metric_values(at)
    assert values["นิสิตที่ผ่านตัวกรอง"] == f"{len(students):,}"
    assert values["GPA เฉลี่ย"] == f"{students['GPA'].mean():.2f}"
    pct = (students["Extracurricular"] == 1).mean() * 100
    assert values["ผู้เข้าร่วมกิจกรรมเสริมหลักสูตร"] == f"{pct:.1f}%"
    assert values["Perception Gap สูงสุด"] == "-1.7"


def test_gpa_filter_updates_kpis():
    at = run_app()
    at.sidebar.slider(key="gpa_range").set_value((3.0, 4.0)).run()
    assert not at.exception
    students = dl.load_student_data().df
    expected = students[students["GPA"].between(3.0, 4.0)]
    values = metric_values(at)
    assert values["นิสิตที่ผ่านตัวกรอง"] == f"{len(expected):,}"
    assert values["GPA เฉลี่ย"] == f"{expected['GPA'].mean():.2f}"


def test_activity_filter_updates_kpis():
    at = run_app()
    at.sidebar.radio(key="activity").set_value("participant").run()
    assert not at.exception
    students = dl.load_student_data().df
    expected = int((students["Extracurricular"] == 1).sum())
    values = metric_values(at)
    assert values["นิสิตที่ผ่านตัวกรอง"] == f"{expected:,}"
    assert values["ผู้เข้าร่วมกิจกรรมเสริมหลักสูตร"] == "100.0%"


def test_empty_filter_result_does_not_crash():
    at = run_app()
    gpa = dl.load_student_data().df["GPA"].sort_values().reset_index(drop=True)
    widest = gpa.diff().idxmax()  # ช่องว่างกว้างสุดระหว่าง GPA สองค่าที่ติดกัน ไม่มีนิสิตอยู่ข้างใน
    lo, hi = float(gpa[widest - 1]), float(gpa[widest])
    middle = (lo + hi) / 2
    at.sidebar.slider(key="gpa_range").set_value((middle - 1e-6, middle + 1e-6)).run()
    values = metric_values(at)
    assert values["นิสิตที่ผ่านตัวกรอง"] == "0"
    assert values["GPA เฉลี่ย"] == "—"
    assert values["ผู้เข้าร่วมกิจกรรมเสริมหลักสูตร"] == "—"
    assert not at.exception
    assert any("ไม่มีนิสิตที่ตรงกับตัวกรอง" in w.value for w in at.warning)


def test_single_group_filter_does_not_crash():
    at = run_app()
    at.sidebar.radio(key="activity").set_value("non_participant").run()
    assert not at.exception
    assert any("กลุ่มเดียว" in i.value for i in at.info)


def test_reset_button_restores_defaults():
    at = run_app()
    at.sidebar.slider(key="gpa_range").set_value((3.0, 4.0)).run()
    at.sidebar.radio(key="activity").set_value("participant").run()
    reset = [b for b in at.sidebar.button if "Reset" in b.label][0]
    reset.click().run()
    assert not at.exception
    assert at.session_state["activity"] == "all"
    assert tuple(at.session_state["gpa_range"]) == dl.gpa_slider_bounds(dl.load_student_data().df)
    assert metric_values(at)["นิสิตที่ผ่านตัวกรอง"] == f"{len(dl.load_student_data().df):,}"


@pytest.mark.parametrize("persona", ["student", "instructor", "employer"])
def test_each_persona_renders(persona):
    at = run_app()
    at.sidebar.selectbox(key="persona").set_value(persona).run()
    assert not at.exception


def test_denominator_switch_and_empty_progression_selection():
    at = run_app()
    at.radio(key="denominator").set_value("with_skills").run()
    assert not at.exception
    at.multiselect(key="progression_skills").set_value([]).run()
    assert not at.exception


def test_missing_data_file_shows_thai_error_without_traceback(tmp_path):
    """คัดลอกโปรเจกต์ไปที่ชั่วคราวโดยไม่มีไฟล์ CSV แล้วตรวจข้อความ error"""
    project = tmp_path / "proj"
    project.mkdir()
    for name in ("app.py", "charts.py", "data_loader.py"):
        shutil.copy(ROOT / name, project / name)
    at = AppTest.from_file(str(project / "app.py"), default_timeout=TIMEOUT)
    # โมดูลเดิมใน sys.modules ชี้ path เดิม จึงบังคับให้โหลดโมดูลใหม่จากโฟลเดอร์ชั่วคราว
    for mod in ("data_loader", "charts"):
        sys.modules.pop(mod, None)
    sys.path.insert(0, str(project))
    try:
        at.run()
    finally:
        sys.path.remove(str(project))
        for mod in ("data_loader", "charts"):
            sys.modules.pop(mod, None)
        sys.path.insert(0, str(ROOT))
    assert not at.exception
    assert len(at.error) == 1
    assert "Student_performance_data.csv" in at.error[0].value
