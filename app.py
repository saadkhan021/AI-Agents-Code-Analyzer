import hashlib
import os
import streamlit as st
from dotenv import load_dotenv
from graph import build_pipeline, initial_state

load_dotenv()

st.set_page_config(page_title="AI Code Review ", page_icon="", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .block-container { padding-top: 1.6rem; max-width: 1180px; }
    #MainMenu, footer { visibility: hidden; }

    .hero {
        background: radial-gradient(circle at 20% 20%, #312e81 0%, #0f172a 60%);
        border-radius: 18px;
        padding: 2rem 2.4rem;
        margin-bottom: 1.6rem;
        color: #f8fafc;
        box-shadow: 0 10px 30px rgba(15, 23, 42, .25);
    }
    .hero h1 { margin: 0; font-size: 1.9rem; font-weight: 800; letter-spacing: -.02em; }
    .hero p { margin: .5rem 0 0 0; color: #a5b4fc; font-size: .95rem; }
    .flow { display: flex; align-items: center; gap: .5rem; margin-top: 1rem; flex-wrap: wrap; }
    .flow-step {
        display: inline-flex; align-items: center; gap: .4rem;
        padding: .35rem .85rem; border-radius: 999px; font-size: .82rem; font-weight: 600;
        background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14); color: #e0e7ff;
    }
    .flow-arrow { color: #6366f1; font-weight: 700; }

    .panel {
        border: 1px solid #e5e7eb; border-radius: 14px; padding: 1.2rem 1.4rem;
        background: #ffffff; box-shadow: 0 1px 2px rgba(0,0,0,.03);
    }

    .stTextArea textarea { font-family: 'JetBrains Mono', monospace !important; font-size: .88rem !important; border-radius: 10px !important; }
    .stButton > button { border-radius: 10px !important; font-weight: 600 !important; }

    .metric-card {
        border: 1px solid #e5e7eb; border-radius: 12px; padding: 1rem;
        text-align: center; background: #fafafa;
    }
    .metric-card .num { font-size: 1.7rem; font-weight: 800; }
    .metric-card .lbl { font-size: .74rem; color: #6b7280; text-transform: uppercase; letter-spacing: .05em; margin-top: .1rem; }
    .m-total .num { color: #1e293b; }
    .m-critical .num { color: #dc2626; }
    .m-high .num { color: #ea580c; }
    .m-medium .num { color: #ca8a04; }
    .m-low .num { color: #65a30d; }

    .sev-badge {
        display: inline-block; padding: .15rem .6rem; border-radius: 999px;
        font-size: .72rem; font-weight: 700; letter-spacing: .03em;
    }
    .sev-critical { background: #fee2e2; color: #b91c1c; }
    .sev-high { background: #ffedd5; color: #c2410c; }
    .sev-medium { background: #fef9c3; color: #a16207; }
    .sev-low { background: #ecfccb; color: #4d7c0f; }

    .cache-note {
        border-radius: 10px; padding: .7rem 1rem; background: #eff6ff;
        border: 1px solid #bfdbfe; color: #1e40af; font-size: .88rem;
    }
    </style>

    <div class="hero">
        <h1> AI-Powered Code Review </h1>
        <p>Three specialist agents work in sequence over your code, each with a narrow,
        schema-constrained job — nothing free-form, nothing invented.</p>
        <div class="flow">
            <span class="flow-step"> Scanner</span>
            <span class="flow-arrow">→</span>
            <span class="flow-step"> Refactor</span>
            <span class="flow-arrow">→</span>
            <span class="flow-step"> Docs</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


APP_BUILD = "v3-no-secrets"  # temporary marker so we can confirm which file is running

GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

if "result_cache" not in st.session_state:
    st.session_state.result_cache = {}


def _cache_key(code: str, language: str) -> str:
    return hashlib.sha256(f"{language}::{code}".encode("utf-8")).hexdigest()


if not GEMINI_API_KEY:
    st.error(
        f"[{APP_BUILD}] No Gemini API key found. Create a `.env` file in this same "
        "folder containing:\n\nGOOGLE_API_KEY=your_key_here"
    )
    st.stop()

with st.sidebar:
    st.markdown("###  Settings")
    language = st.selectbox("Language", ["python", "javascript", "typescript", "java", "go"], index=0)

    st.markdown("---")
    st.markdown("##### Why low hallucination?")
    st.markdown(
        "- Structured JSON-schema output only\n"
        "- Every issue needs exact quoted evidence\n"
        "- temperature = 0 + fixed seed\n"
        "- Identical code reuses the cached result\n"
        "- Refactor agent may only fix reported issues"
    )

    if st.session_state.result_cache:
        st.markdown("---")
        st.caption(f" {len(st.session_state.result_cache)} cached result(s) this session")
        if st.button("Clear cache", use_container_width=True):
            st.session_state.result_cache = {}
            st.rerun()

st.markdown("#### Paste your code")
code_input = st.text_area(
    "Paste your raw code here",
    height=280,
    placeholder="def get_user(id):\n    query = \"SELECT * FROM users WHERE id = \" + id\n    ...",
    label_visibility="collapsed",
)

col1, col2 = st.columns([1, 4])
with col1:
    run_button = st.button(" Run Pipeline", type="primary", use_container_width=True)
with col2:
    force_rerun = st.checkbox("Force fresh run (ignore cache)", value=False)

STEP_LABELS = {
    "scanner": " Scanner Agent — auditing code",
    "refactor": " Refactor Agent — applying fixes",
    "docs": " Docs Agent — generating documentation",
}

if run_button:
    if not code_input.strip():
        st.error("Please paste some code to analyze.")
        st.stop()

    key = _cache_key(code_input, language)
    final_state = None

    if not force_rerun and key in st.session_state.result_cache:
        st.markdown(
            '<div class="cache-note"> Identical code already analyzed this session — '
            "showing the cached result instantly, instead of re-generating.</div>",
            unsafe_allow_html=True,
        )
        final_state = st.session_state.result_cache[key]
    else:
        pipeline = build_pipeline()
        state = initial_state(code_input, language, GEMINI_API_KEY)

        status_placeholders = {
            "scanner": st.status(STEP_LABELS["scanner"], expanded=True),
            "refactor": st.status(STEP_LABELS["refactor"], expanded=False),
            "docs": st.status(STEP_LABELS["docs"], expanded=False),
        }

        try:
            for update in pipeline.stream(state):
                node_name, node_output = next(iter(update.items()))
                box = status_placeholders.get(node_name)
                if box:
                    for line in node_output.get("status_log", [])[-1:]:
                        box.write(line)
                    box.update(state="complete", expanded=False)
                final_state = {**state, **node_output}
                state = final_state
        except Exception as e:
            st.error(f"Pipeline failed: {e}")
            st.stop()

        st.session_state.result_cache[key] = final_state

    st.success("Pipeline complete ")

    report = final_state.get("audit_report") or {}
    issues = report.get("issues", [])
    sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in issues:
        sev = issue.get("severity", "low")
        if sev in sev_counts:
            sev_counts[sev] += 1

    m1, m2, m3, m4, m5 = st.columns(5)
    for col, label, val, cls in [
        (m1, "Total issues", len(issues), "m-total"),
        (m2, "Critical", sev_counts["critical"], "m-critical"),
        (m3, "High", sev_counts["high"], "m-high"),
        (m4, "Medium", sev_counts["medium"], "m-medium"),
        (m5, "Low", sev_counts["low"], "m-low"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card {cls}"><div class="num">{val}</div>'
                f'<div class="lbl">{label}</div></div>',
                unsafe_allow_html=True,
            )

    st.write("")
    tab1, tab2, tab3 = st.tabs([" Audit Report", " Refactored Code", " Documentation"])

    with tab1:
        st.write(report.get("summary", ""))
        if not issues:
            st.info("No issues found.")
        sev_class = {"critical": "sev-critical", "high": "sev-high", "medium": "sev-medium", "low": "sev-low"}
        for i, issue in enumerate(issues, 1):
            sev = issue.get("severity", "low")
            with st.expander(f"#{i}  {issue['category']} — line {issue['line_number']}"):
                st.markdown(
                    f'<span class="sev-badge {sev_class.get(sev, "")}">{sev.upper()}</span>',
                    unsafe_allow_html=True,
                )
                st.code(issue["evidence"], language=language)
                st.write(f"**Problem:** {issue['description']}")
                st.write(f"**Suggestion:** {issue['suggestion']}")

    with tab2:
        st.write("**Changes made:**")
        for c in final_state.get("changes_made") or []:
            st.write(f"- {c}")
        not_fixed = final_state.get("issues_not_fixed") or []
        if not_fixed:
            st.write("**Left for manual review:**")
            for c in not_fixed:
                st.write(f"- {c}")
        refactored_code = final_state.get("refactored_code", "")
        st.code(refactored_code, language=language)
        st.download_button(
            " Download refactored file",
            data=refactored_code,
            file_name=f"refactored.{language}",
            use_container_width=True,
        )

    with tab3:
        st.markdown(final_state.get("readme_markdown", ""))
        st.download_button(
            "Download README.md",
            data=final_state.get("readme_markdown", ""),
            file_name="README.md",
            use_container_width=True,
        )
        st.markdown("---")
        st.write("**Docstring-annotated code:**")
        annotated = final_state.get("docstring_annotated_code", "")
        st.code(annotated, language=language)
        st.download_button(
            "Download annotated file",
            data=annotated,
            file_name=f"annotated.{language}",
            use_container_width=True,
        )

    st.markdown("---")
    with st.expander(" Full pipeline log"):
        for line in final_state.get("status_log", []):
            st.write(line)