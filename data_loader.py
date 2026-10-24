"""โหลด ตรวจสอบ และคำนวณข้อมูลสำหรับ Dashboard

โมดูลนี้ไม่พึ่ง Streamlit เพื่อให้ทดสอบด้วย pytest ได้โดยตรง
การแคชและการแสดงผลอยู่ที่ app.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# ค่าคงที่ (Constants)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STUDENT_FILE = DATA_DIR / "Student_performance_data.csv"
JOB_FILE = DATA_DIR / "job_market_skills_dataset.csv"

STUDENT_REQUIRED_COLUMNS = [
    "StudentID", "GPA", "Extracurricular", "Sports", "Music",
    "Volunteering", "Absences", "StudyTimeWeekly",
]
JOB_REQUIRED_COLUMNS = [
    "job_title", "company", "location", "category",
    "created_date", "description", "skills",
]

GPA_SCALE_MIN = 0.0  # GPA ในชุดข้อมูลอยู่ในสเกล 0.0-4.0
GPA_SCALE_MAX = 4.0
BINARY_FLAG_COLUMNS = ["Extracurricular", "Sports", "Music", "Volunteering"]
ACTIVITY_LABELS = {
    "Extracurricular": "กิจกรรมเสริมหลักสูตร (Extracurricular)",
    "Sports": "กีฬา (Sports)",
    "Music": "ดนตรี (Music)",
    "Volunteering": "จิตอาสา (Volunteering)",
}
MIN_GROUP_SIZE = 30      # ขนาดกลุ่มขั้นต่ำก่อนรายงานช่วงความเชื่อมั่น
Z_95 = 1.96              # ค่า z สำหรับช่วงความเชื่อมั่น 95% (ประมาณด้วยการแจกแจงปกติ)

# Keyword ที่ใช้นับ Soft Skill จากคำอธิบายงาน (regex ใช้ขอบเขตคำ ไม่ใช่ substring)
SOFT_SKILL_PATTERNS = {
    "การทำงานเป็นทีม (Team / Collaboration)":
        r"\b(?:team|teams|teamwork|teammates?|collaborat\w*)\b",
    "การสื่อสาร (Communication)": r"\bcommunicat\w*",
    "การคิดวิเคราะห์ (Analytical)": r"\banalytical\b",
    "ภาวะผู้นำ (Leadership)": r"\bleadership\b",
    "การแก้ปัญหา (Problem solving)": r"\bproblem[- ]solving\b",
    "การวางแผน (Planning)": r"\bplanning\b",
}
SKILL_DISPLAY_OVERRIDES = {
    "sql": "SQL", "numpy": "NumPy", "pytorch": "PyTorch", "tensorflow": "TensorFlow",
}

ACTIVITY_FILTER_OPTIONS = ("all", "participant", "non_participant")


class DataLoadError(Exception):
    """ข้อผิดพลาดที่แสดงให้ผู้ใช้ได้ (message) แยกจากรายละเอียดสำหรับนักพัฒนา (detail)"""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


# ---------------------------------------------------------------------------
# โหลดไฟล์
# ---------------------------------------------------------------------------
def read_csv_checked(path: Path, required_columns: list[str]) -> pd.DataFrame:
    """อ่าน CSV พร้อมตรวจว่าไฟล์มีอยู่และมีคอลัมน์ที่จำเป็นครบ"""
    if not path.is_file():
        raise DataLoadError(
            f"ไม่พบไฟล์ `{path.name}` ที่ตำแหน่ง `{path}` "
            f"กรุณาวางไฟล์ไว้ในโฟลเดอร์ `data/` ตามโครงสร้างโปรเจกต์",
            detail=f"checked path: {path}",
        )
    try:
        df = pd.read_csv(path)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise DataLoadError(
            f"อ่านไฟล์ `{path.name}` ไม่สำเร็จ ไฟล์อาจเสียหายหรือไม่ใช่ CSV",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise DataLoadError(
            f"ไฟล์ `{path.name}` ขาดคอลัมน์ที่จำเป็น: {', '.join(missing)}",
            detail=f"columns found: {list(df.columns)}",
        )
    return df


# ---------------------------------------------------------------------------
# ข้อมูลนิสิต
# ---------------------------------------------------------------------------
@dataclass
class StudentData:
    """ข้อมูลนิสิตที่ผ่านการตรวจสอบ พร้อมบันทึกสิ่งที่ถูกตัดออกและเหตุผล"""

    df: pd.DataFrame
    rows_loaded: int
    notes: list[str] = field(default_factory=list)
    duplicate_ids: int = 0
    null_cells: int = 0
    age_min: int | None = None
    age_max: int | None = None
    grade_class_spearman: float | None = None


def prepare_students(raw: pd.DataFrame) -> StudentData:
    """ตรวจสอบและเตรียมข้อมูลนิสิต

    ไม่เปลี่ยนชื่อคอลัมน์และไม่แก้ค่าใด ๆ ตัดเฉพาะแถวที่ใช้คำนวณไม่ได้
    (GPA/ธงกิจกรรมว่าง ไม่ใช่ตัวเลข หรืออยู่นอกช่วงที่กำหนด) และบันทึกเหตุผลใน notes
    """
    df = raw.copy()
    notes: list[str] = []
    rows_loaded = len(df)

    numeric_cols = ["GPA", "Absences", "StudyTimeWeekly", *BINARY_FLAG_COLUMNS]
    for col in numeric_cols:
        before_na = int(df[col].isna().sum())
        df[col] = pd.to_numeric(df[col], errors="coerce")
        coerced = int(df[col].isna().sum()) - before_na
        if coerced > 0:
            notes.append(f"คอลัมน์ {col}: {coerced} ค่าไม่ใช่ตัวเลข ถูกถือเป็นค่าว่าง")

    required_values = ["GPA", *BINARY_FLAG_COLUMNS]
    keep = df[required_values].notna().all(axis=1)
    if (dropped := int((~keep).sum())) > 0:
        notes.append(f"ตัด {dropped} แถวที่ GPA หรือคอลัมน์กิจกรรม (0/1) ว่าง")

    in_range = df["GPA"].between(GPA_SCALE_MIN, GPA_SCALE_MAX)
    if (out := int((keep & ~in_range).sum())) > 0:
        notes.append(f"ตัด {out} แถวที่ GPA อยู่นอกช่วง {GPA_SCALE_MIN}-{GPA_SCALE_MAX}")
    keep &= in_range

    for col in BINARY_FLAG_COLUMNS:
        is_binary = df[col].isin([0, 1])
        if (bad := int((keep & ~is_binary).sum())) > 0:
            notes.append(f"ตัด {bad} แถวที่ {col} ไม่ใช่ 0/1")
        keep &= is_binary

    df = df.loc[keep].reset_index(drop=True)
    df[BINARY_FLAG_COLUMNS] = df[BINARY_FLAG_COLUMNS].astype(int)

    age_min = age_max = None
    if "Age" in df.columns and pd.api.types.is_numeric_dtype(df["Age"]) and len(df):
        age_min, age_max = int(df["Age"].min()), int(df["Age"].max())

    spearman = None
    if "GradeClass" in df.columns and len(df) > 2:
        # Spearman = Pearson ของอันดับ (ไม่ใช้ method="spearman" เพราะต้องพึ่ง scipy)
        grade_class = pd.to_numeric(df["GradeClass"], errors="coerce")
        value = df["GPA"].rank().corr(grade_class.rank())
        spearman = None if pd.isna(value) else float(value)

    return StudentData(
        df=df,
        rows_loaded=rows_loaded,
        notes=notes,
        duplicate_ids=int(df["StudentID"].duplicated().sum()),
        null_cells=int(raw.isna().sum().sum()),
        age_min=age_min,
        age_max=age_max,
        grade_class_spearman=spearman,
    )


def load_student_data(path: Path = STUDENT_FILE) -> StudentData:
    """โหลดและตรวจสอบข้อมูลนิสิตจากไฟล์ CSV"""
    return prepare_students(read_csv_checked(path, STUDENT_REQUIRED_COLUMNS))


def gpa_slider_bounds(df: pd.DataFrame, step: float = 0.1) -> tuple[float, float]:
    """ขอบเขตของตัวกรอง GPA จากข้อมูลจริง (ปัดออกเป็นขั้น step เพื่อรวมทุกแถว)"""
    if df.empty:
        return GPA_SCALE_MIN, GPA_SCALE_MAX
    lo = math.floor(float(df["GPA"].min()) / step) * step
    hi = math.ceil(float(df["GPA"].max()) / step) * step
    lo, hi = round(max(lo, GPA_SCALE_MIN), 2), round(min(hi, GPA_SCALE_MAX), 2)
    return (lo, hi) if lo < hi else (GPA_SCALE_MIN, GPA_SCALE_MAX)


def normalise_gpa_range(
    value: tuple[float, float], lower: float, upper: float
) -> tuple[float, float]:
    """จำกัดช่วง GPA ให้อยู่ในขอบเขตที่ถูกต้องและเรียงจากน้อยไปมาก"""
    lo, hi = sorted((float(value[0]), float(value[1])))
    return max(lower, lo), min(upper, hi)


def filter_students(
    df: pd.DataFrame, gpa_range: tuple[float, float], activity: str = "all"
) -> pd.DataFrame:
    """กรองนิสิตตามช่วง GPA และสถานะ Extracurricular (คืน DataFrame ใหม่ ไม่แก้ต้นฉบับ)"""
    if activity not in ACTIVITY_FILTER_OPTIONS:
        raise ValueError(f"activity ต้องเป็นหนึ่งใน {ACTIVITY_FILTER_OPTIONS}")
    lo, hi = sorted(gpa_range)
    mask = df["GPA"].between(lo, hi)
    if activity == "participant":
        mask &= df["Extracurricular"] == 1
    elif activity == "non_participant":
        mask &= df["Extracurricular"] == 0
    return df.loc[mask].copy()


def student_kpis(df: pd.DataFrame) -> dict[str, float | int | None]:
    """KPI ระดับนิสิตจาก DataFrame ที่กรองแล้ว (คืน None เมื่อคำนวณไม่ได้)"""
    n = len(df)
    if n == 0:
        return {"n": 0, "mean_gpa": None, "n_active": 0, "pct_active": None}
    n_active = int((df["Extracurricular"] == 1).sum())
    return {
        "n": n,
        "mean_gpa": float(df["GPA"].mean()),
        "n_active": n_active,
        "pct_active": n_active / n * 100,
    }


@dataclass
class MeanDifference:
    """ความต่างของ GPA เฉลี่ย (กลุ่มเข้าร่วม ลบ กลุ่มไม่เข้าร่วม)"""

    diff: float
    ci_low: float
    ci_high: float
    cohens_d: float | None
    n_with: int
    n_without: int

    @property
    def ci_excludes_zero(self) -> bool:
        return self.ci_low > 0 or self.ci_high < 0


def group_summary(df: pd.DataFrame, flag_col: str = "Extracurricular") -> pd.DataFrame:
    """สถิติ GPA ของกลุ่ม 0/1 (n, mean, median, std) คืนครบทั้งสองกลุ่มแม้กลุ่มว่าง"""
    stats = df.groupby(flag_col)["GPA"].agg(["count", "mean", "median", "std"])
    stats = stats.reindex([0, 1])
    stats["count"] = stats["count"].fillna(0).astype(int)
    stats.index.name = flag_col
    return stats


def mean_difference(
    df: pd.DataFrame, flag_col: str = "Extracurricular", min_group_size: int = MIN_GROUP_SIZE
) -> MeanDifference | None:
    """ความต่างของค่าเฉลี่ย GPA พร้อมช่วงความเชื่อมั่น 95% (Welch, ประมาณด้วยค่า z)

    คืน None เมื่อกลุ่มใดมีตัวอย่างน้อยกว่า min_group_size
    ผลนี้เป็นความสัมพันธ์เชิงสังเกต ไม่ได้พิสูจน์เหตุและผล
    """
    with_flag = df.loc[df[flag_col] == 1, "GPA"]
    without_flag = df.loc[df[flag_col] == 0, "GPA"]
    n1, n0 = len(with_flag), len(without_flag)
    if n1 < min_group_size or n0 < min_group_size:
        return None
    diff = float(with_flag.mean() - without_flag.mean())
    se = math.sqrt(with_flag.var(ddof=1) / n1 + without_flag.var(ddof=1) / n0)
    pooled_var = ((n1 - 1) * with_flag.var(ddof=1) + (n0 - 1) * without_flag.var(ddof=1)) / (n1 + n0 - 2)
    d = diff / math.sqrt(pooled_var) if pooled_var > 0 else None
    return MeanDifference(diff, diff - Z_95 * se, diff + Z_95 * se, d, n1, n0)


def activity_gpa_table(df: pd.DataFrame) -> pd.DataFrame:
    """GPA เฉลี่ยของผู้เข้าร่วม/ไม่เข้าร่วมในแต่ละประเภทกิจกรรม (ตัดกลุ่มที่ n = 0)"""
    rows = []
    for col, label in ACTIVITY_LABELS.items():
        for flag, group in ((1, "เข้าร่วม"), (0, "ไม่เข้าร่วม")):
            subset = df.loc[df[col] == flag, "GPA"]
            if len(subset):
                rows.append({"activity": label, "group": group, "n": len(subset),
                             "mean_gpa": float(subset.mean())})
    return pd.DataFrame(rows, columns=["activity", "group", "n", "mean_gpa"])


def covariate_means(df: pd.DataFrame, flag_col: str = "Extracurricular") -> pd.DataFrame:
    """ค่าเฉลี่ยตัวแปรร่วม (ชั่วโมงเรียนต่อสัปดาห์, ขาดเรียน) แยกตามกลุ่ม ใช้เตือนเรื่อง confounding"""
    out = df.groupby(flag_col)[["StudyTimeWeekly", "Absences"]].mean().reindex([0, 1])
    out.index = out.index.map({0: "ไม่เข้าร่วม", 1: "เข้าร่วม"})
    out.columns = ["ชั่วโมงเรียนต่อสัปดาห์ (เฉลี่ย)", "จำนวนวันขาดเรียน (เฉลี่ย)"]
    return out


def safe_correlation(df: pd.DataFrame, col_a: str, col_b: str, min_rows: int = 3) -> float | None:
    """สัมประสิทธิ์สหสัมพันธ์ Pearson คืน None เมื่อข้อมูลน้อยหรือไม่มีความแปรปรวน"""
    if len(df) < min_rows or df[col_a].nunique() < 2 or df[col_b].nunique() < 2:
        return None
    value = df[col_a].corr(df[col_b])
    return None if pd.isna(value) else float(value)


# ---------------------------------------------------------------------------
# ข้อมูลประกาศงาน
# ---------------------------------------------------------------------------
@dataclass
class JobBundle:
    """ตารางที่คำนวณจากประกาศงานล่วงหน้า (คำนวณครั้งเดียวแล้วแคช)"""

    n_postings: int
    n_with_skills: int
    n_duplicates: int
    date_min: str | None
    date_max: str | None
    skill_counts: pd.DataFrame   # skill, postings
    soft_counts: pd.DataFrame    # skill, postings
    top_locations: pd.DataFrame  # location, postings
    top_categories: pd.DataFrame  # category, postings
    max_description_chars: int
    pct_description_at_max: float


def display_skill_name(raw: str) -> str:
    """ชื่อทักษะสำหรับแสดงผล (ไม่เปลี่ยนค่าในข้อมูลต้นฉบับ)"""
    return SKILL_DISPLAY_OVERRIDES.get(raw, raw.title())


def count_listed_skills(jobs: pd.DataFrame) -> pd.DataFrame:
    """นับจำนวนประกาศที่ระบุแต่ละทักษะในคอลัมน์ skills (นับครั้งเดียวต่อประกาศ)"""
    exploded = (
        jobs["skills"].dropna().astype(str).str.split(",").explode()
        .str.strip().str.lower()
    )
    exploded = exploded[exploded != ""]
    unique_per_posting = exploded.reset_index().drop_duplicates()
    counts = unique_per_posting["skills"].value_counts()
    return pd.DataFrame({"skill": counts.index.astype(str), "postings": counts.to_numpy()})


def count_soft_skill_keywords(jobs: pd.DataFrame) -> pd.DataFrame:
    """นับจำนวนประกาศที่คำอธิบายงานมี keyword ของ Soft Skill (ประมาณการจากข้อความ)"""
    desc = jobs["description"].fillna("").astype(str)
    rows = [
        {"skill": label, "postings": int(desc.str.contains(pattern, case=False, regex=True).sum())}
        for label, pattern in SOFT_SKILL_PATTERNS.items()
    ]
    return pd.DataFrame(rows).sort_values("postings", ascending=False, ignore_index=True)


def with_percentage(counts: pd.DataFrame, denominator: int) -> pd.DataFrame:
    """เพิ่มคอลัมน์ pct = postings / denominator * 100 (denominator = 0 ให้ NaN)"""
    out = counts.copy()
    out["pct"] = out["postings"] / denominator * 100 if denominator > 0 else np.nan
    return out


def build_job_bundle(jobs: pd.DataFrame) -> JobBundle:
    """สรุปข้อมูลประกาศงานทั้งหมดที่ Dashboard ต้องใช้"""
    dates = pd.to_datetime(jobs["created_date"], errors="coerce", utc=True)
    desc_len = jobs["description"].fillna("").astype(str).str.len()
    max_len = int(desc_len.max()) if len(desc_len) else 0

    def top(col: str, name: str, n: int = 5) -> pd.DataFrame:
        vc = jobs[col].fillna("(ไม่ระบุ)").value_counts().head(n)
        return pd.DataFrame({name: vc.index.astype(str), "postings": vc.to_numpy()})

    return JobBundle(
        n_postings=len(jobs),
        n_with_skills=int(jobs["skills"].notna().sum()),
        n_duplicates=int(jobs.duplicated(["job_title", "company", "description"]).sum()),
        date_min=None if dates.isna().all() else dates.min().strftime("%Y-%m-%d"),
        date_max=None if dates.isna().all() else dates.max().strftime("%Y-%m-%d"),
        skill_counts=count_listed_skills(jobs),
        soft_counts=count_soft_skill_keywords(jobs),
        top_locations=top("location", "location"),
        top_categories=top("category", "category"),
        max_description_chars=max_len,
        pct_description_at_max=float((desc_len == max_len).mean() * 100) if max_len else 0.0,
    )


def load_job_bundle(path: Path = JOB_FILE) -> JobBundle:
    """โหลดไฟล์ประกาศงานและสรุปผล"""
    return build_job_bundle(read_csv_checked(path, JOB_REQUIRED_COLUMNS))


# ---------------------------------------------------------------------------
# ข้อมูล Benchmark / จำลอง (ไม่มีไฟล์ต้นทางในโปรเจกต์)
# ---------------------------------------------------------------------------
BENCHMARK_NOTE = (
    "ข้อมูล Benchmark: คะแนนชุดนี้ถูกกำหนดไว้ในโค้ดเดิมของโปรเจกต์ ไม่มีไฟล์ข้อมูลต้นทางให้ตรวจสอบ "
    "และไม่ได้รับผลจากตัวกรองในแถบด้านข้าง"
)
SIMULATED_NOTE = (
    "ข้อมูลจำลอง: คะแนนในแต่ละ Phase ถูกกำหนดไว้ในโค้ดเดิมของโปรเจกต์ ไม่ได้มาจากการเก็บข้อมูลที่ตรวจสอบได้ "
    "ใช้เพื่อสาธิตรูปแบบการนำเสนอเท่านั้น"
)

PHASES = ["Phase 1: Pre-Project", "Phase 2: Mid-Project", "Phase 3: Post-Project"]
PROGRESSION_SKILLS = {
    "Groupwork_Skill": "การทำงานกลุ่ม (Groupwork)",
    "Analytical_Skill": "การคิดวิเคราะห์ (Analytical)",
    "Systemic_Planning": "การวางแผนเชิงระบบ (Planning)",
}


def get_perception_benchmark() -> pd.DataFrame:
    """คะแนน Student vs Industry และ Gap = Student - Industry เรียงจาก Gap ติดลบมากสุดก่อน"""
    df = pd.DataFrame({
        "skill": ["การทำงานกลุ่ม (Groupwork)", "การวางแผน (Planning)",
                  "การตั้งคำถามและสื่อสาร (Questioning & Comm.)", "การคิดวิเคราะห์ (Analytical Thinking)"],
        "student_score": [3.1, 3.4, 2.8, 3.9],
        "industry_score": [4.8, 4.6, 4.2, 4.7],
    })
    df["gap"] = (df["student_score"] - df["industry_score"]).round(2)
    return df.sort_values("gap", ignore_index=True)


def get_progression_benchmark() -> pd.DataFrame:
    """คะแนนจำลองของแต่ละทักษะในแต่ละ Phase (รูปแบบ long: phase, skill, score)"""
    wide = pd.DataFrame({
        "phase": PHASES,
        "Groupwork_Skill": [2.5, 3.8, 4.6],
        "Analytical_Skill": [3.0, 3.7, 4.5],
        "Systemic_Planning": [2.2, 3.5, 4.4],
    })
    long = wide.melt(id_vars="phase", var_name="skill_key", value_name="score")
    long["skill"] = long["skill_key"].map(PROGRESSION_SKILLS)
    long["phase"] = pd.Categorical(long["phase"], categories=PHASES, ordered=True)
    return long.drop(columns="skill_key").sort_values(["skill", "phase"], ignore_index=True)


def progression_changes(long: pd.DataFrame) -> pd.DataFrame:
    """การเปลี่ยนแปลงของคะแนนระหว่าง Phase ของแต่ละทักษะ"""
    wide = long.pivot(index="skill", columns="phase", values="score").reindex(columns=PHASES)
    out = pd.DataFrame({
        "Phase 1": wide[PHASES[0]],
        "Phase 2": wide[PHASES[1]],
        "Phase 3": wide[PHASES[2]],
        "เปลี่ยน Phase 1→2": wide[PHASES[1]] - wide[PHASES[0]],
        "เปลี่ยน Phase 2→3": wide[PHASES[2]] - wide[PHASES[1]],
    }).round(2)
    return out.reset_index()
