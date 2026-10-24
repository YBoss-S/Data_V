"""Unlocking Student Potential: Dashboard วิเคราะห์ทักษะนิสิตเทียบกับความต้องการตลาดแรงงาน

รัน: python -m streamlit run app.py
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

import charts
import data_loader as dl

PERSONA_LABELS = {
    "student": "นิสิต (Student)",
    "instructor": "อาจารย์ผู้สอน (Instructor)",
    "employer": "ผู้ประกอบการ (Employer)",
}
ACTIVITY_FILTER_LABELS = {
    "all": "ทั้งหมด",
    "participant": "เข้าร่วมกิจกรรม (Extracurricular = 1)",
    "non_participant": "ไม่เข้าร่วมกิจกรรม (Extracurricular = 0)",
}
DENOMINATOR_LABELS = {
    "all": "ทุกประกาศ",
    "with_skills": "เฉพาะประกาศที่ระบุทักษะในคอลัมน์ skills",
}
PERSONA_KPIS = {  # ชุด KPI ของแต่ละมุมมอง (key อ้างอิงใน build_kpi_cards)
    "student": ["records", "gpa", "gap", "top_skill"],
    "instructor": ["records", "gpa", "active", "gpa_diff"],
    "employer": ["postings", "skills_listed", "top_skill", "team"],
}
PERSONA_TAB_ORDER = {  # แท็บแรกคือแท็บที่เปิดอยู่เมื่อเข้าหน้านี้
    "student": ["gap", "gpa", "demand", "progression", "quality"],
    "instructor": ["progression", "gpa", "gap", "demand", "quality"],
    "employer": ["demand", "gap", "progression", "gpa", "quality"],
}
PERSONA_FINDING_ORDER = {
    "student": ["gap", "hard", "soft", "activity", "absence"],
    "instructor": ["activity", "absence", "gap", "hard", "soft"],
    "employer": ["hard", "soft", "gap", "activity", "absence"],
}
TAB_LABELS = {
    "gap": "Perception Gap", "demand": "Industry Skill Demand", "progression": "Skill Progression",
    "gpa": "GPA & Extracurricular", "quality": "คุณภาพข้อมูล",
}
TOP_N_SKILLS = 10  # จำนวนทักษะสูงสุดที่แสดงในกราฟจัดอันดับ
DEFAULT_ACTIVITY = "all"


# ---------------------------------------------------------------------------
# โหลดข้อมูล (แคชด้วย path + เวลาแก้ไขไฟล์ ไม่ขึ้นกับตัวกรองของผู้ใช้)
# ---------------------------------------------------------------------------
def _mtime(path: Path) -> float:
    """เวลาแก้ไขไฟล์ ใช้เป็น cache key ให้โหลดใหม่เมื่อไฟล์เปลี่ยน (0.0 ถ้าไม่มีไฟล์)"""
    return path.stat().st_mtime if path.is_file() else 0.0


@st.cache_data(show_spinner="กำลังโหลดข้อมูลนิสิต...")
def cached_student_data(path: str, modified_time: float) -> dl.StudentData:
    return dl.load_student_data(Path(path))


@st.cache_data(show_spinner="กำลังสรุปข้อมูลประกาศงาน...")
def cached_job_bundle(path: str, modified_time: float) -> dl.JobBundle:
    return dl.load_job_bundle(Path(path))


def load_everything() -> tuple[dl.StudentData, dl.JobBundle]:
    """โหลดข้อมูลทั้งสองชุด หากผิดพลาดแสดงข้อความภาษาไทยและหยุดแอปโดยไม่แสดง Traceback"""
    try:
        students = cached_student_data(str(dl.STUDENT_FILE), _mtime(dl.STUDENT_FILE))
        jobs = cached_job_bundle(str(dl.JOB_FILE), _mtime(dl.JOB_FILE))
    except dl.DataLoadError as exc:
        st.error(f"โหลดข้อมูลไม่สำเร็จ: {exc.message}")
        if exc.detail:
            with st.expander("รายละเอียดสำหรับนักพัฒนา"):
                st.code(exc.detail)
        st.stop()
    return students, jobs


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def reset_filters(default_range: tuple[float, float]) -> None:
    """คืนค่าตัวกรองเป็นค่าเริ่มต้น (เรียกผ่าน on_click ก่อน rerun)"""
    st.session_state["gpa_range"] = default_range
    st.session_state["activity"] = DEFAULT_ACTIVITY


def render_sidebar(students: dl.StudentData, jobs: dl.JobBundle) -> tuple[str, tuple[float, float], str]:
    """วาด Sidebar และคืนค่า (persona, gpa_range, activity)"""
    bounds = dl.gpa_slider_bounds(students.df)
    with st.sidebar:
        st.header("ตัวเลือกการแสดงผล")
        persona = st.selectbox(
            "มุมมองผู้ใช้ (User Persona)", options=list(PERSONA_LABELS),
            format_func=PERSONA_LABELS.get, key="persona",
            help="เปลี่ยนชุด KPI ลำดับแท็บ ลำดับข้อค้นพบ และข้อเสนอแนะ ส่วนตัวเลขของแต่ละกราฟคำนวณจากข้อมูลเดิม",
        )

        st.subheader("ตัวกรองข้อมูลนิสิต")
        st.slider(
            "ช่วงเกรดเฉลี่ย (GPA)", min_value=bounds[0], max_value=bounds[1],
            value=bounds, step=0.05, key="gpa_range",
            help="ขอบเขตกำหนดจาก GPA ต่ำสุด–สูงสุดในข้อมูลจริง",
        )
        st.radio(
            "การเข้าร่วมกิจกรรมเสริมหลักสูตร", options=list(ACTIVITY_FILTER_LABELS),
            format_func=ACTIVITY_FILTER_LABELS.get, key="activity",
        )
        st.button("รีเซ็ตตัวกรอง (Reset Filters)", on_click=reset_filters, args=(bounds,),
                  width="stretch")

        with st.expander("เกี่ยวกับชุดข้อมูล"):
            st.markdown(
                f"**ข้อมูลนิสิต:** {len(students.df):,} ระเบียน "
                f"(อายุ {students.age_min}–{students.age_max} ปี) "
                "ไม่มีคอลัมน์วันที่ จึงระบุช่วงเวลาไม่ได้\n\n"
                f"**ประกาศงาน:** {jobs.n_postings:,} รายการ "
                f"สร้างระหว่าง {jobs.date_min} ถึง {jobs.date_max}\n\n"
                "ตัวกรองมีผลกับข้อมูลนิสิตเท่านั้น ข้อมูลประกาศงานและคะแนน Benchmark "
                "แสดงทั้งชุดเสมอ"
            )
        st.caption("รายวิชา 01219482 การอธิบายข้อมูลด้วยภาพ | Project Workshop")
    return persona, st.session_state["gpa_range"], st.session_state["activity"]


# ---------------------------------------------------------------------------
# Header + KPI
# ---------------------------------------------------------------------------
def render_header(students: dl.StudentData, jobs: dl.JobBundle) -> None:
    st.title("Unlocking Student Potential")
    st.markdown(
        "**แดชบอร์ดวิเคราะห์พัฒนาการทักษะของนิสิตเทียบกับความต้องการของตลาดแรงงาน** "
        "ครอบคลุมผลการเรียน (GPA) กิจกรรมเสริมหลักสูตร ช่องว่างการรับรู้ทักษะ (Perception Gap) "
        "และทักษะที่ปรากฏในประกาศงาน"
    )
    st.caption(
        f"ชุดข้อมูล: นิสิต {len(students.df):,} ระเบียน · ประกาศงาน {jobs.n_postings:,} รายการ "
        f"({jobs.date_min} ถึง {jobs.date_max}) · "
        "คะแนน Perception Gap และ Skill Progression เป็นข้อมูล Benchmark/จำลอง"
    )


@dataclass(frozen=True)
class KpiCard:
    """ข้อมูลของ KPI หนึ่งใบ (ค่าและคำอธิบายถูกคำนวณไว้แล้ว)"""

    label: str
    value: str
    caption: str
    help: str


def _top_skill_card(jobs: dl.JobBundle) -> KpiCard:
    help_text = "ทักษะเทคนิคที่ปรากฏในคอลัมน์ skills ของประกาศงานมากที่สุด ไม่ได้รับผลจากตัวกรองนิสิต"
    if jobs.skill_counts.empty or jobs.n_postings == 0:
        return KpiCard("ทักษะเทคนิคที่ถูกระบุมากสุด", "—", "ไม่มีข้อมูลทักษะ", help_text)
    top = jobs.skill_counts.iloc[0]
    return KpiCard("ทักษะเทคนิคที่ถูกระบุมากสุด", dl.display_skill_name(top["skill"]),
                   f"{top['postings'] / jobs.n_postings * 100:.1f}% ของ {jobs.n_postings:,} ประกาศ", help_text)


def _team_keyword_card(jobs: dl.JobBundle) -> KpiCard:
    help_text = ("ร้อยละของประกาศที่คำอธิบายงานมีคำว่า team / teamwork / collaborat* (ค้นด้วย keyword "
                 "ในคำอธิบายที่ถูกตัดความยาว จึงเป็นค่าประมาณขั้นต่ำ) ไม่ได้รับผลจากตัวกรองนิสิต")
    row = jobs.soft_counts[jobs.soft_counts["skill"].str.contains("Team")]
    if row.empty or jobs.n_postings == 0:
        return KpiCard("ประกาศที่กล่าวถึงการทำงานเป็นทีม", "—", "ไม่มีข้อมูล", help_text)
    return KpiCard("ประกาศที่กล่าวถึงการทำงานเป็นทีม",
                   f"{row.iloc[0]['postings'] / jobs.n_postings * 100:.1f}%",
                   "จาก keyword ในคำอธิบายงาน", help_text)


def build_kpi_cards(
    persona: str, filtered: pd.DataFrame, total_rows: int, benchmark: pd.DataFrame, jobs: dl.JobBundle
) -> list[KpiCard]:
    """สร้างชุด KPI ตามมุมมองผู้ใช้ (ทุกใบคำนวณจากข้อมูลจริง หรือระบุว่าเป็น Benchmark)"""
    kpi = dl.student_kpis(filtered)
    widest = benchmark.iloc[0]  # เรียงตาม gap น้อยสุด (ติดลบมากสุด) ไว้แล้ว
    diff = dl.mean_difference(filtered) if kpi["n"] else None
    cards = {
        "records": KpiCard(
            "นิสิตที่ผ่านตัวกรอง", f"{kpi['n']:,}", f"จากทั้งหมด {total_rows:,} คน",
            "จำนวนแถวในข้อมูลนิสิตที่อยู่ในช่วง GPA และกลุ่มกิจกรรมที่เลือก"),
        "gpa": KpiCard(
            "GPA เฉลี่ย", "—" if kpi["mean_gpa"] is None else f"{kpi['mean_gpa']:.2f}", "สเกล 0.00–4.00",
            "ค่าเฉลี่ยของ GPA ของนิสิตที่ผ่านตัวกรอง (สเกล 0-4)"),
        "active": KpiCard(
            "ผู้เข้าร่วมกิจกรรมเสริมหลักสูตร",
            "—" if kpi["pct_active"] is None else f"{kpi['pct_active']:.1f}%",
            f"{kpi['n_active']:,} จาก {kpi['n']:,} คน",
            "จำนวนนิสิตที่ Extracurricular = 1 หารด้วยนิสิตที่ผ่านตัวกรอง"),
        "gap": KpiCard(
            "Perception Gap สูงสุด", f"{widest['gap']:+.1f}", f"{widest['skill']} (Benchmark)",
            f"Gap = คะแนนนิสิต − คะแนนตลาดแรงงาน ค่าติดลบ = นิสิตประเมินต่ำกว่าที่ตลาดต้องการ "
            f"({widest['skill']}: นิสิต {widest['student_score']:.1f} vs ตลาด {widest['industry_score']:.1f}) "
            "ข้อมูล Benchmark ไม่ถูกกรอง"),
        "gpa_diff": KpiCard(
            "ความต่าง GPA (เข้าร่วม − ไม่เข้าร่วม)",
            "—" if diff is None else f"{diff.diff:+.2f}",
            f"ต้องมีกลุ่มละ ≥ {dl.MIN_GROUP_SIZE} คน" if diff is None
            else f"95% CI {diff.ci_low:+.2f} ถึง {diff.ci_high:+.2f}",
            "ความต่างของ GPA เฉลี่ยระหว่างกลุ่มเข้าร่วมกับไม่เข้าร่วมกิจกรรม เป็นความสัมพันธ์ ไม่ใช่สาเหตุ"),
        "postings": KpiCard(
            "ประกาศงานที่วิเคราะห์", f"{jobs.n_postings:,}", f"{jobs.date_min} ถึง {jobs.date_max}",
            "จำนวนแถวในไฟล์ประกาศงาน (รวมประกาศที่ซ้ำกัน) ไม่ได้รับผลจากตัวกรองนิสิต"),
        "skills_listed": KpiCard(
            "ประกาศที่ระบุทักษะ",
            "—" if jobs.n_postings == 0 else f"{jobs.n_with_skills / jobs.n_postings * 100:.1f}%",
            f"{jobs.n_with_skills:,} จาก {jobs.n_postings:,} ประกาศ",
            "ร้อยละของประกาศที่คอลัมน์ skills ไม่ว่าง ประกาศที่เหลือไม่มีข้อมูลทักษะเทคนิค"),
        "top_skill": _top_skill_card(jobs),
        "team": _team_keyword_card(jobs),
    }
    return [cards[key] for key in PERSONA_KPIS[persona]]


def render_kpis(cards: list[KpiCard], persona: str) -> None:
    """วาด KPI เป็นแถวเดียว (Streamlit จะเรียงซ้อนอัตโนมัติบนจอแคบ)"""
    if persona == "employer":
        st.caption("มุมมองนี้เน้นข้อมูลประกาศงานทั้งชุด ตัวกรองนิสิตมีผลกับแท็บ GPA & Extracurricular เท่านั้น")
    for column, card in zip(st.columns(len(cards)), cards):
        with column.container(border=True):
            st.metric(card.label, card.value, help=card.help)
            st.caption(card.caption)



# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
def render_gap(benchmark: pd.DataFrame) -> None:
    st.subheader("Perception Gap Analysis")
    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(charts.perception_gap_chart(benchmark), width="stretch")
    with right:
        st.markdown(
            "**Gap = คะแนนนิสิต − คะแนนตลาดแรงงาน** เครื่องหมายลบ (−) หมายถึงนิสิตประเมินต่ำกว่าที่ตลาดต้องการ "
            "เครื่องหมายบวก (+) คือสูงกว่า"
        )
        table = benchmark.rename(columns={
            "skill": "ทักษะ", "student_score": "นิสิต", "industry_score": "ตลาด", "gap": "Gap"})
        st.dataframe(table, hide_index=True, width="stretch",
                     column_config={"Gap": st.column_config.NumberColumn(format="%+.1f")})
        st.info(dl.BENCHMARK_NOTE, icon=":material/info:")


def render_demand(jobs: dl.JobBundle) -> None:
    st.subheader("Industry Skill Demand")
    basis = st.radio(
        "ฐานคำนวณร้อยละของทักษะเทคนิค", options=list(DENOMINATOR_LABELS), format_func=DENOMINATOR_LABELS.get,
        horizontal=True, key="denominator",
        help=f"{jobs.n_postings - jobs.n_with_skills:,} จาก {jobs.n_postings:,} ประกาศไม่มีข้อมูลในคอลัมน์ skills จึงให้เลือกฐานคำนวณได้",
    )
    denominator = jobs.n_postings if basis == "all" else jobs.n_with_skills
    hard = dl.with_percentage(jobs.skill_counts.head(TOP_N_SKILLS), denominator)
    hard["label"] = hard["skill"].map(dl.display_skill_name)
    soft = dl.with_percentage(jobs.soft_counts, jobs.n_postings).rename(columns={"skill": "label"})

    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            charts.skill_demand_chart(
                hard, f"ทักษะเทคนิคในคอลัมน์ skills (ฐาน {denominator:,} ประกาศ)", "ร้อยละของประกาศงาน (%)"),
            width="stretch",
        )
        st.caption(
            "แหล่งที่มา: `job_market_skills_dataset.csv` คอลัมน์ `skills` · "
            f"{jobs.n_with_skills:,} จาก {jobs.n_postings:,} ประกาศระบุทักษะ · "
            "ประกาศหนึ่งอาจระบุหลายทักษะ ร้อยละจึงรวมกันเกิน 100% ได้"
        )
    with right:
        st.plotly_chart(
            charts.skill_demand_chart(
                soft, f"Soft Skill ที่พบ keyword ในคำอธิบายงาน (ฐาน {jobs.n_postings:,} ประกาศ)",
                "ร้อยละของประกาศงาน (%)"),
            width="stretch",
        )
        st.caption(
            "ประมาณการจากการค้นคำในคอลัมน์ `description` ด้วยขอบเขตคำ (เช่น team, teamwork, collaborat*) · "
            f"คำอธิบาย {jobs.pct_description_at_max:.0f}% ถูกตัดที่ {jobs.max_description_chars} ตัวอักษร "
            "ตัวเลขจึงเป็นค่าต่ำสุดโดยประมาณ ไม่ใช่สัดส่วนความต้องการจริง"
        )
    st.caption("ข้อมูลทั้งสองกราฟเป็นข้อมูลระดับตลาดแรงงาน แยกจากข้อมูลนิสิต จึงไม่ได้รับผลจากตัวกรองใน Sidebar")


def render_progression() -> None:
    st.subheader("Skill Progression")
    st.warning(dl.SIMULATED_NOTE, icon=":material/warning:")
    long = dl.get_progression_benchmark()
    all_skills = list(long["skill"].unique())
    selected = st.multiselect("เลือกทักษะที่ต้องการแสดง", options=all_skills, default=all_skills,
                              key="progression_skills")
    if not selected:
        st.info("กรุณาเลือกอย่างน้อย 1 ทักษะ")
        return
    st.plotly_chart(charts.progression_chart(long, selected), width="stretch")
    changes = dl.progression_changes(long)
    changes = changes[changes["skill"].isin(selected)].rename(columns={"skill": "ทักษะ"})
    st.dataframe(
        changes, hide_index=True, width="stretch",
        column_config={c: st.column_config.NumberColumn(format="%+.1f") for c in changes.columns
                       if c.startswith("เปลี่ยน")},
    )
    st.caption("ค่าในตารางเป็นผลต่างของคะแนนจำลองระหว่าง Phase ไม่ใช่ผลของกิจกรรมใดโดยเฉพาะ")


def render_gpa_activity(filtered: pd.DataFrame) -> None:
    st.subheader("GPA และกิจกรรมเสริมหลักสูตร")
    if filtered.empty:
        st.warning("ไม่มีนิสิตที่ตรงกับตัวกรองที่เลือก กรุณาปรับช่วง GPA หรือกดรีเซ็ตตัวกรอง",
                   icon=":material/search_off:")
        return

    summary = dl.group_summary(filtered)
    if (summary["count"] == 0).any():
        st.info("ตัวกรองปัจจุบันเหลือนิสิตเพียงกลุ่มเดียว (เข้าร่วม หรือ ไม่เข้าร่วม) จึงยังเปรียบเทียบสองกลุ่มไม่ได้",
                icon=":material/info:")

    left, right = st.columns(2)
    left.plotly_chart(charts.gpa_box_chart(filtered), width="stretch")
    right.plotly_chart(charts.gpa_histogram_chart(filtered), width="stretch")

    stats_col, chart_col = st.columns([2, 3])
    with stats_col:
        st.markdown("**สถิติประกอบ**")
        display = summary.rename(index={0: "ไม่เข้าร่วม", 1: "เข้าร่วม"}).rename(columns={
            "count": "จำนวน (n)", "mean": "GPA เฉลี่ย", "median": "มัธยฐาน", "std": "SD"})
        st.dataframe(display, width="stretch", column_config={
            "GPA เฉลี่ย": st.column_config.NumberColumn(format="%.2f"),
            "มัธยฐาน": st.column_config.NumberColumn(format="%.2f"),
            "SD": st.column_config.NumberColumn(format="%.2f"),
        })
        diff = dl.mean_difference(filtered)
        if diff is None:
            st.caption(f"ต้องมีนิสิตอย่างน้อยกลุ่มละ {dl.MIN_GROUP_SIZE} คน จึงจะแสดงความต่างและช่วงความเชื่อมั่น")
        else:
            st.metric("ความต่าง GPA เฉลี่ย (เข้าร่วม − ไม่เข้าร่วม)", f"{diff.diff:+.2f}",
                      help="ช่วงความเชื่อมั่น 95% คำนวณแบบ Welch โดยประมาณด้วยค่า z = 1.96")
            st.caption(f"ช่วงความเชื่อมั่น 95%: {diff.ci_low:+.2f} ถึง {diff.ci_high:+.2f}"
                       + (f" · Cohen's d = {diff.cohens_d:.2f}" if diff.cohens_d is not None else ""))
        st.markdown("**ตัวแปรร่วมที่ควรพิจารณา**")
        st.dataframe(dl.covariate_means(filtered), width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.1f")
                                    for c in ("ชั่วโมงเรียนต่อสัปดาห์ (เฉลี่ย)", "จำนวนวันขาดเรียน (เฉลี่ย)")})
    with chart_col:
        st.plotly_chart(charts.activity_gpa_chart(dl.activity_gpa_table(filtered)), width="stretch")

    st.caption(
        "ข้อมูลนี้เป็นข้อมูลเชิงสังเกต แสดงความสัมพันธ์ระหว่างกิจกรรมกับ GPA เท่านั้น "
        "ไม่สามารถสรุปได้ว่ากิจกรรมเป็นสาเหตุให้ GPA สูงขึ้น"
    )


def render_data_quality(students: dl.StudentData, jobs: dl.JobBundle) -> None:
    st.subheader("คุณภาพข้อมูลและข้อจำกัด")
    left, right = st.columns(2)
    with left:
        st.markdown("**ข้อมูลนิสิต** (`Student_performance_data.csv`)")
        st.markdown(
            f"- แถวที่โหลด {students.rows_loaded:,} · ใช้งาน {len(students.df):,}\n"
            f"- ค่าว่างทั้งไฟล์ {students.null_cells:,} ช่อง · StudentID ซ้ำ {students.duplicate_ids:,}\n"
            f"- อายุ {students.age_min}–{students.age_max} ปี (เป็นวัยมัธยมศึกษา ไม่ใช่ระดับอุดมศึกษา)\n"
            "- ไม่มีคอลัมน์วันที่ จึงวิเคราะห์แนวโน้มตามเวลาไม่ได้"
        )
        if students.notes:
            st.warning("การทำความสะอาดข้อมูล:\n\n" + "\n".join(f"- {n}" for n in students.notes))
        else:
            st.success("ไม่มีการตัดหรือแก้ไขข้อมูลนิสิต", icon=":material/check_circle:")
        if students.grade_class_spearman is not None:
            st.markdown(
                f"- คอลัมน์ `GradeClass` มีสหสัมพันธ์ Spearman กับ GPA = {students.grade_class_spearman:.2f} "
                "แต่ช่วง GPA ของแต่ละ GradeClass ทับซ้อนกันมาก และไม่มีคำอธิบายความหมายของรหัส "
                "แดชบอร์ดจึง **ไม่ใช้** คอลัมน์นี้"
            )
        st.markdown(
            "- `Extracurricular` เป็นธงแยกจาก `Sports`, `Music`, `Volunteering` "
            "(นิสิตที่ Extracurricular = 0 อาจมี Sports/Music/Volunteering = 1) "
            "ไม่มีเอกสารอธิบายนิยามของแต่ละคอลัมน์"
        )
    with right:
        st.markdown("**ข้อมูลประกาศงาน** (`job_market_skills_dataset.csv`)")
        locations = ", ".join(f"{r.location} ({r.postings:,})" for r in jobs.top_locations.head(3).itertuples())
        categories = ", ".join(f"{r.category} ({r.postings:,})" for r in jobs.top_categories.head(2).itertuples())
        st.markdown(
            f"- {jobs.n_postings:,} ประกาศ · ระบุทักษะ {jobs.n_with_skills:,} ประกาศ\n"
            f"- ประกาศที่ชื่อตำแหน่ง บริษัท และคำอธิบายซ้ำกัน {jobs.n_duplicates:,} รายการ "
            "(ยังรวมอยู่ในการคำนวณ ไม่ได้ลบ)\n"
            f"- หมวดหลัก: {categories}\n"
            f"- สถานที่ที่พบมากสุด: {locations}\n"
            "- คอลัมน์ `avg_salary` ว่างทั้งหมด จึงไม่วิเคราะห์เงินเดือน\n"
            "- ข้อมูลเน้นตำแหน่งสายข้อมูล/IT และสถานที่ในอินเดีย อาจไม่แทนตลาดแรงงานไทยหรือสาขาอื่น"
        )
        st.markdown("**ข้อมูล Benchmark/จำลอง**")
        st.markdown("- Perception Gap และ Skill Progression ไม่มีไฟล์ข้อมูลต้นทางในโปรเจกต์")


# ---------------------------------------------------------------------------
# Insights & Recommendations
# ---------------------------------------------------------------------------
def render_insights(
    persona: str, filtered: pd.DataFrame, jobs: dl.JobBundle, benchmark: pd.DataFrame
) -> None:
    st.divider()
    st.header("Insights & Recommendations")

    widest = benchmark.iloc[0]
    top_hard = jobs.skill_counts.head(2)
    team_row = jobs.soft_counts[jobs.soft_counts["skill"].str.contains("Team")]
    diff = dl.mean_difference(filtered) if not filtered.empty else None
    corr_absence = dl.safe_correlation(filtered, "GPA", "Absences")

    st.subheader("ข้อค้นพบจากข้อมูล (Findings)")
    findings: dict[str, str] = {}
    if diff is not None:
        verdict = ("ช่วงความเชื่อมั่นไม่ครอบคลุม 0" if diff.ci_excludes_zero
                   else "ช่วงความเชื่อมั่นครอบคลุม 0")
        findings["activity"] = (
            f"ในนิสิตที่ผ่านตัวกรอง ({diff.n_with + diff.n_without:,} คน) GPA เฉลี่ยของผู้เข้าร่วมกิจกรรมต่างจากผู้ไม่เข้าร่วม "
            f"**{diff.diff:+.2f}** (95% CI {diff.ci_low:+.2f} ถึง {diff.ci_high:+.2f}, {verdict}) "
            "เป็นความสัมพันธ์เชิงสังเกต ไม่ใช่ผลเชิงสาเหตุ")
    else:
        findings["activity"] = "ตัวกรองปัจจุบันมีนิสิตไม่พอสำหรับเปรียบเทียบกลุ่มเข้าร่วมกับไม่เข้าร่วม"
    if corr_absence is not None:
        findings["absence"] = (
            f"จำนวนวันขาดเรียนมีสหสัมพันธ์กับ GPA ที่ r = **{corr_absence:+.2f}** "
            "ในนิสิตที่ผ่านตัวกรอง (ตัวแปรร่วมที่ควรพิจารณาเมื่อตีความผลกิจกรรม)")
    if len(top_hard) == 2:
        a_row, b_row = top_hard.iloc[0], top_hard.iloc[1]
        findings["hard"] = (
            f"ทักษะเทคนิคที่ระบุบ่อยสุดในประกาศงานคือ **{dl.display_skill_name(a_row['skill'])}** "
            f"({a_row['postings'] / jobs.n_postings * 100:.1f}% ของ {jobs.n_postings:,} ประกาศ) และ "
            f"**{dl.display_skill_name(b_row['skill'])}** ({b_row['postings'] / jobs.n_postings * 100:.1f}%)")
    if len(team_row):
        findings["soft"] = (
            f"คำอธิบายงาน **{team_row.iloc[0]['postings'] / jobs.n_postings * 100:.1f}%** มีคำเกี่ยวกับการทำงานเป็นทีม "
            "(ค้นด้วย keyword ในคำอธิบายที่ถูกตัดความยาว จึงเป็นค่าประมาณขั้นต่ำ)")
    findings["gap"] = (
        f"ตามคะแนน Benchmark ช่องว่างใหญ่สุดคือ **{widest['skill']}** (Gap {widest['gap']:+.1f}) "
        "แต่คะแนนชุดนี้ไม่มีไฟล์ข้อมูลต้นทางให้ตรวจสอบ")
    with st.container(border=True):
        for key in PERSONA_FINDING_ORDER[persona]:
            if key in findings:
                st.markdown(f"- {findings[key]}")

    st.subheader(f"ข้อเสนอแนะสำหรับ{PERSONA_LABELS[persona]}")
    st.caption("ข้อเสนอแนะและสมมติฐานต่อไปนี้ไม่ใช่ผลวิเคราะห์โดยตรง ควรทดสอบหรือยืนยันก่อนนำไปใช้")
    recommendations = {
        "student": [
            "ฝึกงานกลุ่มโดยวางแผนร่วมกันตั้งแต่ต้นโปรเจกต์ เพราะการทำงานเป็นทีมเป็นคำที่พบบ่อยในประกาศงาน",
            "ลองฝึกทักษะเครื่องมือที่ประกาศงานระบุบ่อย เช่น SQL และ Python ควบคู่กับรายวิชา",
            "ขอ Feedback จากเพื่อนกลางโปรเจกต์ (สมมติฐาน: ช่วยปิดช่องว่างด้านการสื่อสารและการทำงานกลุ่ม)",
        ],
        "instructor": [
            "เพิ่มจุดประเมินกลางโปรเจกต์ (Mid-Project Checkpoint) เพื่อเก็บข้อมูลพัฒนาการทักษะจริง "
            "แทนการใช้คะแนนจำลอง",
            "ออกแบบ Rubric ที่วัดกระบวนการทำงานกลุ่มควบคู่กับผลงาน",
            "เก็บข้อมูลกิจกรรมพร้อมวันที่และนิยามที่ชัดเจน เพื่อให้วิเคราะห์ความสัมพันธ์กับ GPA ได้แม่นยำขึ้น",
        ],
        "employer": [
            "ระบุทักษะเชิงพฤติกรรม (Soft Skills) ในประกาศงานให้ชัดเจน เพราะข้อมูลประกาศงานปัจจุบันระบุทักษะเพียงบางส่วน",
            "ร่วมกับสถาบันการศึกษาจัดโจทย์จริงให้นิสิตทำ (สมมติฐาน: ช่วยลด Perception Gap)",
            "ให้ Mentor ร่วมประเมินกลางโปรเจกต์ เพื่อให้ข้อมูลเทียบกับความคาดหวังของตลาดได้ตรงขึ้น",
        ],
    }[persona]
    with st.container(border=True):
        for line in recommendations:
            st.markdown(f"- {line}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Unlocking Student Potential | Dashboard", page_icon="📊",
                       layout="wide", initial_sidebar_state="expanded")
    students, jobs = load_everything()
    persona, gpa_range, activity = render_sidebar(students, jobs)

    bounds = dl.gpa_slider_bounds(students.df)
    gpa_range = dl.normalise_gpa_range(gpa_range, *bounds)
    filtered = dl.filter_students(students.df, gpa_range, activity)
    benchmark = dl.get_perception_benchmark()

    render_header(students, jobs)
    render_kpis(build_kpi_cards(persona, filtered, len(students.df), benchmark, jobs), persona)

    renderers = {
        "gap": lambda: render_gap(benchmark),
        "demand": lambda: render_demand(jobs),
        "progression": render_progression,
        "gpa": lambda: render_gpa_activity(filtered),
        "quality": lambda: render_data_quality(students, jobs),
    }
    order = PERSONA_TAB_ORDER[persona]
    for key, tab in zip(order, st.tabs([TAB_LABELS[k] for k in order])):
        with tab:
            renderers[key]()

    render_insights(persona, filtered, jobs, benchmark)


main()
