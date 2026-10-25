"""Run with streamlit run; bootstrap is the only infrastructure composition entry."""

import json
import os
from typing import Any
from uuid import UUID, uuid4

import streamlit as st

from lazyresearch.application.mission_models import MissionEvidence
from lazyresearch.application.relevance_models import Relevance
from lazyresearch.application.workspace import Workspace
from lazyresearch.bootstrap import build_workspace, system_health
from lazyresearch.domain.actions import ActionStatus, Deadline
from lazyresearch.ui.presenters import (
    GROUPS,
    action_description,
    claim_text,
    deadline,
    error_message,
    inputs,
    mission_status,
    plain,
    ranking_mode,
    ranking_reason,
    receipt_status,
    safe_url,
)


def source_details(work: Workspace, identity: UUID) -> None:
    source = work.reads.source(work.owner, identity)
    if source is None:
        st.info("Source unavailable.")
        return
    st.caption(f"{source.source_type} · saved {source.captured_at:%d %b %Y %H:%M %Z}")
    st.write(
        f"Extraction: {source.extraction_status.capitalize()} · "
        f"Analysis: {source.processing_status.capitalize()}"
    )
    if url := safe_url(source.url):
        st.link_button("Open original URL", url, key=f"original-{identity}")
    st.markdown(
        plain(source.text[:12000] or "No extracted text is available. The original was saved.")
    )
    if len(source.text) > 12000:
        st.caption("Showing the first 12,000 extracted characters.")
    if source.analysis:
        st.markdown("**Generated summary**")
        for text in source.analysis.summaries:
            st.markdown(plain(text))
        st.caption("Topics: " + plain(", ".join(source.analysis.topics)))
        st.caption("Analysis coverage: " + source.analysis.coverage)
        for proposal in source.analysis.proposals:
            st.markdown(plain("Proposed action: " + proposal.title))
            if proposal.deadline.raw_text:
                st.caption("Detected deadline: " + plain(proposal.deadline.raw_text))
    if source.failed_job and st.button("Retry failed analysis", key=f"retry-{identity}"):
        work.reads.retry_analysis(work.owner, source.failed_job)
        st.success("Retry queued. Use Analyze next source to run it.")


def add_sources(work: Workspace) -> None:
    st.header("Add Sources")
    st.write("Save URLs, documents and notes first. Analyze them when you are ready.")
    st.caption("Email/Gmail is not connected yet. Paste email text or upload a supported export.")
    if st.button("Load sample sources"):
        st.session_state["receipt"] = work.load_demo()
        st.session_state.pop("ranking", None)
    collections = dict(work.reads.collections(work.owner))
    with st.form("add-sources"):
        urls = st.text_area("URLs — one per line", placeholder="https://example.com/battery-guide")
        uploads = st.file_uploader(
            "TXT, Markdown or PDF files",
            type=["txt", "md", "markdown", "pdf"],
            accept_multiple_files=True,
            max_upload_size=max(1, work.intake.limits.max_upload_bytes // (1024 * 1024)),
        )
        title = st.text_input(
            "Title for pasted text (optional)", placeholder="Home battery installer notes"
        )
        text = st.text_area(
            "Pasted text",
            placeholder="Paste notes, an article excerpt or exported email text here…",
        )
        collection = st.selectbox(
            "Collection (optional)",
            [None, *collections],
            format_func=lambda value: collections[value] if value else "No collection",
        )
        submitted = st.form_submit_button("Save sources", type="primary")
    if submitted:
        entries = inputs(urls, tuple((f.name, f.getvalue()) for f in uploads), text, title)
        if not entries:
            st.info("Add a URL, a file or some text first.")
        else:
            with st.spinner("Saving sources and extracting text…"):
                receipt = work.add(str(uuid4()), entries, collection=collection)
            st.session_state["receipt"] = receipt
            st.session_state.pop("ranking", None)
    last_receipt = st.session_state.get("receipt")
    if last_receipt:
        st.subheader("Submission results")
        for i, entry in enumerate(last_receipt.entries, 1):
            st.write(f"{i}. {receipt_status(entry)}")
            if entry.message:
                st.caption(entry.message)
    st.subheader("Saved sources")
    st.caption(
        "Analysis runs here only when you press the button. It may take a "
        "minute per source; this is not a background queue runner."
    )
    if st.button("Analyze next source"):
        with st.spinner("Analyzing one saved source with the configured model…"):
            outcome = work.process()
        if outcome.startswith("FAILED"):
            st.warning(
                "Analysis failed or the model is unavailable. The original "
                "remains saved. Retry from its source details."
            )
        elif outcome == "IDLE":
            st.info("No pending source analysis.")
        else:
            st.success("Analysis ready.")
        st.session_state.pop("ranking", None)
    with st.spinner("Loading your saved sources…", show_time=True):
        sources = work.reads.sources(work.owner)
    if not sources:
        st.info("No saved sources yet. Add your first source above.")
    for source in sources:
        panel = st.expander(
            plain(source.title) + " · " + source.processing_status.capitalize(),
            key=f"saved-source-{source.id}",
            on_change="rerun",
        )
        if panel.open:
            with panel:
                source_details(work, source.id)


def catch_up(work: Workspace) -> None:
    st.header("What Matters")
    if notice := st.session_state.pop("feedback-notice", None):
        st.success(notice)
    interests = st.text_input(
        "Interests (optional, comma-separated exact topics)",
        placeholder="Home energy, batteries, warranties",
    )
    if st.button("Refresh What Matters", type="primary") or "ranking" not in st.session_state:
        with st.spinner("Finding what matters…"):
            st.session_state["ranking"] = work.catch_up(
                tuple(t.strip() for t in interests.split(",") if t.strip())
            )
    decisions = st.session_state["ranking"]
    if not decisions:
        st.info(
            "Nothing unreviewed right now. Add sources or inspect reviewed "
            "items under Add Sources. Proposed actions remain on Actions."
        )
        st.caption(ranking_mode("BASELINE"))
        return
    for mode in sorted({d.mode for d in decisions}):
        st.info(ranking_mode(mode))
    for label, heading in GROUPS.items():
        items = [d for d in decisions if d.label.value == label]
        if not items:
            continue
        st.subheader(f"{heading} · {len(items)}")
        for decision in items:
            source = work.reads.source(work.owner, decision.item.content_id)
            if source is None:
                continue
            st.markdown("**" + plain(source.title) + "**")
            if decision.deadline_visible:
                st.warning(
                    "Potential deadline — review the source and Actions, even "
                    "if this item is low priority."
                )
            elif decision.item.features.has_action:
                st.info("A source-backed action is available on Actions.")
            st.caption(" · ".join(ranking_reason(r) for r in decision.reasons))
            panel = st.expander("Inspect source", key=f"inspect-{decision.id}", on_change="rerun")
            if panel.open:
                with panel:
                    source_details(work, source.id)
            with st.form(f"feedback-{decision.id}"):
                correction = st.selectbox(
                    "Your choice",
                    list(GROUPS),
                    format_func=lambda value: GROUPS[value],
                    index=list(GROUPS).index(label),
                )
                if st.form_submit_button("Save feedback"):
                    key = f"feedback-event-{decision.item.content_id}"
                    event = work.feedback(
                        decision, Relevance(correction), expected_event=st.session_state.get(key)
                    )
                    st.session_state[key] = event
                    updated = work.reviewed(
                        decision.item.content_id,
                        tuple(t.strip() for t in interests.split(",") if t.strip()),
                    )
                    st.session_state["ranking"] = tuple(
                        updated if d.item.content_id == decision.item.content_id else d
                        for d in decisions
                        if updated or d.item.content_id != decision.item.content_id
                    )
                    st.session_state["feedback-notice"] = (
                        "Explicit feedback saved. Your choice is shown below."
                    )
                    st.rerun()


def evidence(work: Workspace, raw: dict[str, Any]) -> None:
    e = MissionEvidence.model_validate_json(json.dumps(raw))
    resolved = work.reads.evidence(work.owner, e.locator())
    if resolved is None:
        st.warning("This evidence is no longer available.")
        return
    title, url = resolved
    st.markdown("**" + plain(title) + "**")
    st.caption(
        ("Public source" if e.origin == "PUBLIC" else "Saved personal source")
        + (f" · page {e.page}" if e.page else "")
        + " · exact saved extraction"
    )
    st.markdown(plain(e.quote))
    if link := safe_url(url):
        st.link_button("Open source URL", link, key=f"url-{e.id}-{uuid4()}")


def render_result(work: Workspace, result: Any) -> None:
    st.caption(
        f"Published version {result.version} · research run {result.run_sequence} · "
        f"{result.published_at:%d %b %Y %H:%M %Z}"
    )
    if result.coverage == "PARTIAL":
        st.warning(
            "Partial coverage: some information or sources were unavailable. "
            "Review the limitations below."
        )
    p = result.payload
    registry = {str(e["id"]): e for e in p["evidence"]}
    for name in (
        "answer",
        "summary",
        "findings",
        "comparisons",
        "recommendations",
        "claims",
        "action_candidates",
    ):
        value = p["brief"].get(name)
        if not value:
            continue
        st.subheader(
            {"action_candidates": "Proposed actions", "claims": "Additional claims"}.get(
                name, name.capitalize()
            )
        )
        for index, claim in enumerate(value if isinstance(value, list) else [value], 1):
            st.markdown(
                plain(claim_text(claim.get("text", claim.get("title", "")), tuple(registry)))
            )
            if "description" in claim:
                description = action_description(
                    claim.get("text", claim.get("title", "")), claim["description"]
                )
                if description:
                    st.markdown(plain(description))
            st.caption("Evidence links validated; factual support is unreviewed.")
            panel = st.expander(
                f"Evidence for {name.replace('_', ' ')} {index}",
                key=f"claim-{result.id}-{name}-{index}",
                on_change="rerun",
            )
            if panel.open:
                with panel:
                    for identity in claim["evidence"]:
                        evidence(work, registry[str(identity)])
    contradictions = p.get("contradictions", {}).get("conflicts", [])
    if contradictions:
        st.subheader("Possible contradictions")
        for conflict_index, conflict in enumerate(contradictions):
            st.markdown(plain(conflict["description"]))
            st.caption("Unresolved · heuristic detection")
            panel = st.expander(
                "Inspect conflicting evidence",
                key=f"conflict-{result.id}-{conflict_index}",
                on_change="rerun",
            )
            if panel.open:
                with panel:
                    for key in ("evidence_a", "evidence_b"):
                        if str(conflict[key]) in registry:
                            evidence(work, registry[str(conflict[key])])
    for key, title in (
        ("open_questions", "Open questions"),
        ("missing_information", "Missing information"),
    ):
        if p["brief"].get(key):
            st.subheader(title)
            for line in p["brief"][key]:
                st.markdown(plain(claim_text(line, tuple(registry))))
    limits = p.get("limitations", [])
    if limits:
        st.subheader("Coverage limitations")
        for line in limits:
            st.markdown(plain(line.replace("_", " ")))
    st.subheader("What changed")
    if result.baseline_version is None:
        st.caption("First brief — no earlier baseline to compare.")
    else:
        st.caption(
            f"Compared with the frozen baseline: version {result.baseline_version}. "
            "Comparisons are heuristic; missing evidence does not mean a claim became false."
        )
    changes = p.get("changes", {})
    for key, label in (
        ("new_sources", "New sources"),
        ("changed_snapshots", "Updated evidence"),
        ("new_claims", "New findings"),
        ("removed_claims", "Findings absent this run"),
        ("changed_claims", "Changed findings"),
        ("new_actions", "New actions"),
        ("changed_actions", "Changed actions"),
    ):
        if changes.get(key):
            st.markdown("**" + label + "**")
            for value in changes[key]:
                if isinstance(value, dict):
                    st.markdown(plain("Before: " + value["before"] + " · Now: " + value["after"]))
                else:
                    source = next(
                        (e for e in registry.values() if str(e["content_id"]) == str(value)), None
                    )
                    st.markdown(
                        plain(
                            source["title"] or "Untitled source"
                            if source
                            else "Saved source"
                            if len(str(value)) == 36
                            else str(value)
                        )
                    )
    if changes.get("recommendations_changed"):
        st.write("Recommendations changed. See the recommendations and previous brief.")
    if "MODEL_ONLY_CHANGE" in changes.get("categories", []):
        st.info("Model-only changes were detected; source evidence did not change.")


def research(work: Workspace) -> None:
    st.header("Research")
    st.caption(
        "Research continues through the separate research worker, even when you leave this page. "
        "Requests are saved in PostgreSQL; refresh to read actual progress. "
        "Worker availability is not confirmed here. Use System status to check service access."
    )
    with st.form("new-topic"):
        title = st.text_input("New topic name", placeholder="Home battery decision")
        if st.form_submit_button("Create topic"):
            work.mission_commands.create_topic(work.owner, title.strip())
            st.success("Topic created.")
    with st.spinner("Opening your research…", show_time=True):
        topics = work.reads.topics(work.owner)
    if not topics:
        st.info("Create a topic for your first research question.")
        return
    topics_by_id = {t.id: t for t in topics}
    topic_id = st.selectbox(
        "Research topic",
        list(topics_by_id),
        format_func=lambda identity: topics_by_id[identity].title,
    )
    topic = topics_by_id[topic_id]
    with st.form("mission"):
        question = st.text_area(
            "Research question",
            max_chars=500,
            placeholder="Should I buy a 10 kWh home battery now, and what should I verify first?",
        )
        public = st.checkbox("Allow current public web search", value=False)
        collections = dict(work.reads.collections(work.owner))
        selected_collections = st.multiselect(
            "Limit to collections (optional)",
            list(collections),
            format_func=lambda value: collections[value],
        )
        if not work.public_available:
            st.caption(
                "Current web search is unavailable: no search key is "
                "configured. Saved-source research remains available; public "
                "gaps will be disclosed."
            )
        if st.form_submit_button("Start research", type="primary"):
            with st.spinner("Saving your research request…", show_time=True):
                work.research(
                    topic.id, question, public=public, collections=tuple(selected_collections)
                )
            st.success(
                "Request saved. Research continues through the research worker. "
                "Refresh to follow progress."
            )
    st.button("Refresh research")
    for mission in work.reads.missions(work.owner, topic.id):
        st.markdown("**" + plain(mission.question) + "**")
        st.write(mission_status(mission.status, mission.stage))
        if mission.status == "QUEUED":
            st.caption(
                "Waiting for the research service. If this stays queued, "
                "check the worker/server setup in README."
            )
        if mission.status == "FAILED":
            st.warning(
                "Research could not finish. Check the configured "
                "model/research services and try a new request. Your previous "
                "brief is retained."
            )
        if mission.status in {"QUEUED", "RUNNING"}:
            if st.button("Cancel research", key=f"cancel-{mission.id}"):
                work.cancel(mission.id)
                st.rerun()
    with st.spinner("Loading your briefs and history…", show_time=True):
        versions = work.reads.results(work.owner, topic.id)
    if not versions:
        st.info("No published brief yet. Results appear here after research completes.")
        return
    names = {
        r.id: ("Current Brief" if r.id == topic.current_result_id else "Previous version")
        + f" · v{r.version}"
        for r in versions
    }
    by_id = {r.id: r for r in versions}
    selection_key = f"brief-selection-{topic.id}"
    pointer_key = f"brief-current-{topic.id}"
    if (
        st.session_state.get(pointer_key) != topic.current_result_id
        or st.session_state.get(selection_key) not in by_id
    ):
        st.session_state[selection_key] = (
            topic.current_result_id if topic.current_result_id in by_id else versions[0].id
        )
        st.session_state[pointer_key] = topic.current_result_id
    selected_id = st.selectbox(
        "Brief history",
        list(by_id),
        key=selection_key,
        format_func=lambda identity: names[identity],
    )
    render_result(work, by_id[selected_id])


def actions(work: Workspace) -> None:
    st.header("Actions")
    st.caption(
        "Review source-backed proposals. Accepting or completing an action "
        "records your decision here."
    )
    with st.spinner("Loading your actions…", show_time=True):
        items = work.actions()
    if not items:
        st.info(
            "No proposed actions yet. Analyze a source with an explicit task "
            "or complete a research mission."
        )
    for item in items:
        st.markdown("**" + plain(item.title) + "**")
        if description := action_description(item.title, item.description):
            st.markdown(plain(description))
        st.caption(
            f"{item.status.value.capitalize()} · {plain(deadline(item))} · "
            f"candidate uncertainty: {item.proposal.uncertainty}"
        )
        panel = st.expander("Source provenance", key=f"provenance-{item.id}", on_change="rerun")
        if panel.open:
            with panel:
                st.caption(
                    "From source analysis"
                    if item.proposal.origin.analysis_id
                    else "From a published research brief"
                )
                st.caption("Original proposed title: " + plain(item.proposal.title))
                st.caption("Original deadline: " + plain(item.proposal.deadline.raw_text or "None"))
                for locator in item.proposal.evidence:
                    resolved = work.reads.evidence(work.owner, locator)
                    if resolved:
                        st.markdown("**" + plain(resolved[0]) + "**")
                        if locator.page:
                            st.caption(f"Page {locator.page}")
                        st.markdown(plain(locator.quote))
        targets = {
            ActionStatus.PROPOSED: [
                ("Accept", ActionStatus.ACCEPTED),
                ("Dismiss", ActionStatus.DISMISSED),
            ],
            ActionStatus.ACCEPTED: [
                ("Complete", ActionStatus.COMPLETED),
                ("Dismiss", ActionStatus.DISMISSED),
            ],
            ActionStatus.COMPLETED: [("Reopen", ActionStatus.ACCEPTED)],
            ActionStatus.DISMISSED: [("Reopen", ActionStatus.ACCEPTED)],
        }
        cols = st.columns(len(targets[item.status]))
        for col, (label, target) in zip(cols, targets[item.status], strict=True):
            if col.button(label, key=f"{label}-{item.id}-{item.revision}"):
                work.change_action(item, target)
                st.rerun()
        with st.expander("Edit your task", key=f"edit-{item.id}"):
            with st.form(f"edit-form-{item.id}-{item.revision}"):
                title = st.text_input("Task title", item.title)
                description = st.text_area("Task notes", item.description)
                raw_deadline = st.text_input(
                    "Deadline wording (blank clears deadline)", item.deadline.raw_text or ""
                )
                if st.form_submit_button("Save task edits"):
                    work.change_action(
                        item,
                        title=title,
                        description=description,
                        deadline=(
                            item.deadline
                            if raw_deadline.strip() == (item.deadline.raw_text or "")
                            else Deadline(raw_text=raw_deadline.strip() or None)
                        ),
                    )
                    st.rerun()


SECTIONS = {
    "Add Sources": add_sources,
    "What Matters": catch_up,
    "Research": research,
    "Actions": actions,
}

NAVIGATION_CSS = """
<style>
.st-key-workspace-navigation button {
    width: 100%; min-height: 3rem; justify-content: flex-start;
    text-align: left; border: 1px solid transparent;
}
.st-key-workspace-navigation button[kind="primary"] {
    background: #00E300; color: #101810; border-color: #00E300;
}
.st-key-workspace-navigation button[kind="primary"] p { color: #101810; }
.st-key-workspace-navigation button:hover { border-color: #00E300; }
.st-key-workspace-navigation button[kind="tertiary"]:hover { color: inherit; }
.st-key-workspace-navigation button:focus-visible {
    outline: 3px solid #168716; outline-offset: 3px;
}
</style>
"""


def select_section(section: str) -> None:
    st.session_state["workspace-section"] = section


@st.fragment(key="workspace-content")
def workspace_content() -> None:
    # This fragment owns navigation and page content; the app header stays outside it.
    section = st.session_state.get("workspace-section", "Add Sources")
    if section not in SECTIONS:
        section = "Add Sources"
        st.session_state["workspace-section"] = section
    with st.sidebar.container(key="workspace-navigation"):
        st.caption("Workspace")
        for label in SECTIONS:
            st.button(
                label,
                key=f"nav-{label}",
                width="stretch",
                type="primary" if label == section else "tertiary",
                on_click=select_section,
                args=(label,),
            )
    try:
        if "workspace" not in st.session_state:
            st.session_state["workspace"] = build_workspace()
        work = st.session_state["workspace"]
        SECTIONS[section](work)
    except Exception as exc:
        st.error(error_message(exc))
        st.caption("Check DATABASE_URL, migrations and local services in README.")
        if st.button("Refresh workspace"):
            st.session_state.pop("workspace", None)
            st.session_state.pop("ranking", None)
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="LazyResearch OS", page_icon="📚", layout="centered")
    st.html(NAVIGATION_CSS)
    st.title("LazyResearch OS")
    st.caption("Save the reading. Find what matters. Keep the evidence.")
    if os.environ.get("APP_ENV") == "demo":
        st.warning(
            "Public demo: one shared synthetic workspace, no authentication. "
            "Uploaded and saved data persists in Neon (PostgreSQL), not temporary browser storage. "
            "Anyone with the URL can read and change this workspace. "
            "Use synthetic/demo material only. Do NOT upload personal or private information. "
            "Research needs the separately supervised worker and model host, which may be offline."
        )
    st.sidebar.caption("Synthetic/demo workspace · no authentication")
    with st.sidebar.expander("System status"):
        if st.button("Check services"):
            with st.spinner("Checking service access…", show_time=True):
                for item in system_health():
                    st.write(f"{'✅' if item.ok else '⚠️'} {item.name}: {item.detail}")
    workspace_content()


if __name__ == "__main__":
    main()
