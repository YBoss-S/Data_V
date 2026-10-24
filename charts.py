"""ฟังก์ชันสร้างกราฟ Plotly (ไม่พึ่ง Streamlit) ให้สไตล์เป็นมาตรฐานเดียวกัน"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# สีตามพาเลตของโปรเจกต์
COLOR_PRIMARY = "#1E293B"
COLOR_BLUE = "#3B82F6"
COLOR_SUCCESS = "#10B981"
COLOR_WARNING = "#F59E0B"
COLOR_TEXT = "#0F172A"
COLOR_MUTED = "#64748B"
COLOR_GRID = "#E2E8F0"

FONT_FAMILY = "Sarabun, Noto Sans Thai, Segoe UI, Arial, sans-serif"
HISTOGRAM_BIN_SIZE = 0.25  # ความกว้างช่วง GPA ของฮิสโตแกรม
PROGRESSION_STYLE = {  # สี + สัญลักษณ์ + ลายเส้น ต่างกันในแต่ละทักษะ ไม่พึ่งสีอย่างเดียว
    "การทำงานกลุ่ม (Groupwork)": (COLOR_BLUE, "circle", "solid"),
    "การคิดวิเคราะห์ (Analytical)": (COLOR_SUCCESS, "square", "dash"),
    "การวางแผนเชิงระบบ (Planning)": (COLOR_WARNING, "diamond", "dot"),
}


def _style(fig: go.Figure, title: str, height: int = 380, legend_top: bool = True) -> go.Figure:
    """ตั้งค่า Template, Font, Margin, Gridline, Legend ให้เหมือนกันทุกกราฟ"""
    fig.update_layout(
        template="plotly_white",
        title=dict(text=title, x=0, xanchor="left", font=dict(size=16, color=COLOR_TEXT)),
        height=height,
        margin=dict(l=10, r=20, t=70 if legend_top else 50, b=40),
        font=dict(family=FONT_FAMILY, size=13, color=COLOR_TEXT),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(font_family=FONT_FAMILY),
    )
    if legend_top:
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                      xanchor="left", x=0, title_text=""))
    fig.update_xaxes(gridcolor=COLOR_GRID, zerolinecolor=COLOR_GRID)
    fig.update_yaxes(gridcolor=COLOR_GRID, zerolinecolor=COLOR_GRID)
    return fig


def perception_gap_chart(df: pd.DataFrame) -> go.Figure:
    """Grouped horizontal bar: Student vs Industry (แกนคะแนน 0-5 เดียวกัน เรียงตาม Gap)"""
    fig = go.Figure()
    for column, name, color in (
        ("student_score", "นิสิตประเมิน (Student)", COLOR_BLUE),
        ("industry_score", "ตลาดแรงงานต้องการ (Industry)", COLOR_PRIMARY),
    ):
        fig.add_trace(go.Bar(
            y=df["skill"], x=df[column], name=name, orientation="h",
            marker_color=color, text=df[column].map("{:.1f}".format), textposition="outside",
            customdata=df[["gap"]],
            hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:.1f}} / 5"
                          "<br>Gap (Student − Industry): %{customdata[0]:+.1f}<extra></extra>",
        ))
    fig.update_layout(barmode="group", bargap=0.35)
    fig.update_xaxes(title_text="คะแนน (สเกล 1-5)", range=[0, 5.5], dtick=1)
    fig.update_yaxes(autorange="reversed", title_text="")  # Gap ติดลบมากสุดอยู่บนสุด
    return _style(fig, "คะแนนทักษะ: นิสิต เทียบ ตลาดแรงงาน (เรียงตาม Gap)", height=400)


def skill_demand_chart(
    df: pd.DataFrame, title: str, x_title: str, label_col: str = "label"
) -> go.Figure:
    """Horizontal bar จัดอันดับทักษะ เรียงมาก→น้อย (ต้องมีคอลัมน์ label, postings, pct)"""
    data = df.sort_values("pct", ascending=False)
    upper = float(data["pct"].max()) * 1.2 if len(data) and data["pct"].notna().any() else 1.0
    fig = go.Figure(go.Bar(
        y=data[label_col], x=data["pct"], orientation="h", marker_color=COLOR_BLUE,
        text=data["pct"].map("{:.1f}%".format), textposition="outside", cliponaxis=False,
        customdata=data[["postings"]],
        hovertemplate="<b>%{y}</b><br>%{x:.1f}% ของประกาศ (%{customdata[0]:,} ประกาศ)<extra></extra>",
    ))
    fig.update_xaxes(title_text=x_title, range=[0, upper], ticksuffix="%")
    fig.update_yaxes(autorange="reversed", title_text="")
    return _style(fig, title, height=380, legend_top=False)


def progression_chart(long: pd.DataFrame, selected_skills: list[str]) -> go.Figure:
    """Line chart พัฒนาการต่อ Phase เรียงลำดับ Phase ตามที่กำหนด"""
    fig = go.Figure()
    phases = list(long["phase"].cat.categories)
    for skill in selected_skills:
        subset = long[long["skill"] == skill].sort_values("phase")
        color, symbol, dash = PROGRESSION_STYLE.get(skill, (COLOR_MUTED, "circle", "solid"))
        fig.add_trace(go.Scatter(
            x=subset["phase"].astype(str), y=subset["score"], name=skill,
            mode="lines+markers+text", text=subset["score"].map("{:.1f}".format),
            textposition="top center",
            line=dict(color=color, width=3, dash=dash),
            marker=dict(color=color, size=10, symbol=symbol),
            hovertemplate=f"<b>{skill}</b><br>%{{x}}<br>คะแนน: %{{y:.1f}} / 5<extra></extra>",
        ))
    fig.update_xaxes(title_text="ระยะของโปรเจกต์ (Phase)", categoryorder="array", categoryarray=phases)
    fig.update_yaxes(title_text="คะแนนทักษะ (สเกล 1-5)", range=[1, 5.2], dtick=1)
    return _style(fig, "พัฒนาการทักษะแต่ละ Phase (ข้อมูลจำลอง)", height=420)


def gpa_box_chart(df: pd.DataFrame) -> go.Figure:
    """Box plot GPA แยกตามกลุ่มกิจกรรม แสดง n ในป้ายแกน x (ข้ามกลุ่มที่ไม่มีข้อมูล)"""
    fig = go.Figure()
    for flag, name, color in ((0, "ไม่เข้าร่วม", COLOR_MUTED), (1, "เข้าร่วม", COLOR_BLUE)):
        gpa = df.loc[df["Extracurricular"] == flag, "GPA"]
        if gpa.empty:
            continue
        fig.add_trace(go.Box(
            y=gpa, name=f"{name} (n={len(gpa):,})", marker_color=color, boxmean=True,
            hovertemplate=f"{name}<br>GPA: %{{y:.2f}}<extra></extra>",
        ))
    fig.update_yaxes(title_text="เกรดเฉลี่ย (GPA, สเกล 0-4)", range=[-0.1, 4.1])
    fig.update_xaxes(title_text="กิจกรรมเสริมหลักสูตร (Extracurricular)")
    fig.update_layout(showlegend=False)
    return _style(fig, "การกระจายของ GPA ตามการเข้าร่วมกิจกรรม", legend_top=False)


def gpa_histogram_chart(df: pd.DataFrame) -> go.Figure:
    """Histogram GPA ซ้อนกัน แสดงเป็นร้อยละภายในกลุ่ม เพื่อเทียบกลุ่มขนาดต่างกันได้"""
    fig = go.Figure()
    for flag, name, color in ((0, "ไม่เข้าร่วม", COLOR_MUTED), (1, "เข้าร่วม", COLOR_BLUE)):
        gpa = df.loc[df["Extracurricular"] == flag, "GPA"]
        if gpa.empty:
            continue
        fig.add_trace(go.Histogram(
            x=gpa, name=f"{name} (n={len(gpa):,})", marker_color=color, opacity=0.6,
            histnorm="percent", xbins=dict(size=HISTOGRAM_BIN_SIZE),
            hovertemplate=f"{name}<br>GPA ช่วง %{{x}}<br>%{{y:.1f}}% ของกลุ่ม<extra></extra>",
        ))
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title_text="เกรดเฉลี่ย (GPA, สเกล 0-4)", range=[0, 4.1])
    fig.update_yaxes(title_text="ร้อยละของนิสิตในกลุ่ม (%)")
    return _style(fig, "สัดส่วนนิสิตในแต่ละช่วง GPA", legend_top=True)


def activity_gpa_chart(table: pd.DataFrame) -> go.Figure:
    """Grouped bar: GPA เฉลี่ยของผู้เข้าร่วม/ไม่เข้าร่วมในแต่ละประเภทกิจกรรม"""
    fig = go.Figure()
    for group, color in (("ไม่เข้าร่วม", COLOR_MUTED), ("เข้าร่วม", COLOR_BLUE)):
        subset = table[table["group"] == group]
        fig.add_trace(go.Bar(
            x=subset["activity"], y=subset["mean_gpa"], name=group, marker_color=color,
            text=subset["mean_gpa"].map("{:.2f}".format), textposition="outside",
            customdata=subset[["n"]],
            hovertemplate=f"<b>%{{x}}</b><br>{group}: GPA เฉลี่ย %{{y:.2f}}"
                          "<br>n = %{customdata[0]:,}<extra></extra>",
        ))
    fig.update_layout(barmode="group")
    fig.update_yaxes(title_text="GPA เฉลี่ย (สเกล 0-4)", range=[0, 4])
    fig.update_xaxes(title_text="ประเภทกิจกรรม")
    return _style(fig, "GPA เฉลี่ยจำแนกตามประเภทกิจกรรม", height=400)
