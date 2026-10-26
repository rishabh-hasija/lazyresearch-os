"""Run with streamlit run; bootstrap is the only infrastructure composition entry."""

import json
import logging
import os
import traceback
from typing import Any
from uuid import UUID, uuid4

import streamlit as st

from lazyresearch.application.mission_models import MissionEvidence
from lazyresearch.application.relevance_models import Relevance
from lazyresearch.application.workspace import Workspace
from lazyresearch.application.workspace_models import MissionView
from lazyresearch.bootstrap import build_workspace, system_health
from lazyresearch.domain.actions import ActionStatus, Deadline
from lazyresearch.ports.errors import RepositoryError
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


def create_source_collection(work: Workspace) -> None:
    try:
        identity = work.create_collection(st.session_state.get("new-collection-name", ""))
    except ValueError:
        st.session_state["collection-error"] = "Enter a collection name (up to 120 characters)."
    except Exception as exc:
        # Never log names, source text, credentials, SQL parameters or exception messages.
        cause: BaseException | None = exc
        while cause is not None:
            logging.getLogger(__name__).error(
                "collection_create_failed exception=%s attribute=%s sqlstate=%s frames=%s",
                type(cause).__name__,
                getattr(cause, "name", None) if isinstance(cause, AttributeError) else None,
                getattr(cause, "sqlstate", None),
                [
                    (frame.filename, frame.lineno, frame.name)
                    for frame in traceback.extract_tb(cause.__traceback__)
                ],
            )
            cause = cause.__cause__
        st.session_state["collection-error"] = error_message(exc)
    else:
        st.session_state["source-collection"] = identity
        st.session_state["workspace-collection"] = identity
        st.session_state["collection-editor-open"] = False
        st.session_state.pop("collection-error", None)
        st.session_state["collection-notice"] = "Collection ready and selected."


def add_sources(work: Workspace) -> None:
    st.header("Add Sources")
    st.write("Save URLs, documents and notes first. Analyze them when you are ready.")
    st.caption(
        "Email connection isn’t available yet. You can paste email text or upload a supported file."
    )
    if st.button("Load sample sources"):
        st.session_state["receipt"] = work.load_demo()
        st.session_state.pop("ranking", None)
    collections, active = active_collection(work)
    if st.session_state.get("source-context") != active:
        st.session_state["source-collection"] = active
        st.session_state["source-context"] = active
    if st.session_state.get("source-collection") not in collections:
        st.session_state["source-collection"] = None
    with st.form("add-sources"):
        urls = st.text_area(
            "URLs — one per line",
            placeholder="https://example.com/article",
            help="Multiple URLs are allowed. Enter one URL per line.",
        )
        uploads = st.file_uploader(
            "TXT, Markdown or PDF files",
            type=["txt", "md", "markdown", "pdf"],
            accept_multiple_files=True,
            help="Upload multiple TXT, Markdown, or PDF files together.",
            max_upload_size=max(1, work.intake.limits.max_upload_bytes // (1024 * 1024)),
        )
        title = st.text_input(
            "Title for pasted text (optional)", placeholder="e.g. Notes from a meeting"
        )
        text = st.text_area(
            "Pasted text",
            placeholder=(
                "Paste an email, note, article excerpt, meeting notes, or any text you want "
                "LazyResearch to organize..."
            ),
        )
        st.caption(
            "Best results: save one email, note, or article at a time. If you combine several "
            "text blocks, separate them clearly. They'll still be stored as one source."
        )
        collection = st.selectbox(
            "Collection (optional)",
            [None, *collections],
            key="source-collection",
            format_func=lambda value: collections[value] if value else "No collection",
        )
        save_column, create_column = st.columns(2)
        with save_column:
            submitted = st.form_submit_button("Save sources", type="primary")
        with create_column:
            if st.form_submit_button("+ Create collection"):
                st.session_state["collection-editor-open"] = True
                st.session_state.pop("collection-error", None)
    if st.session_state.get("collection-editor-open"):
        with st.form("create-source-collection"):
            st.text_input(
                "Collection name",
                placeholder="e.g. Office software",
                max_chars=120,
                key="new-collection-name",
            )
            st.form_submit_button(
                "Create collection",
                on_click=create_source_collection,
                args=(work,),
            )
        if message := st.session_state.get("collection-error"):
            st.warning(message)
    if notice := st.session_state.pop("collection-notice", None):
        st.success(notice)
    if submitted:
        entries = inputs(urls, tuple((f.name, f.getvalue()) for f in uploads), text, title)
        if not entries:
            st.info("Add a URL, a file or some text first.")
        else:
            with st.spinner("Saving sources and extracting text…"):
                receipt = work.add(str(uuid4()), entries, collection=collection)
            st.session_state["receipt"] = receipt
            if collection and any(entry.content_id for entry in receipt.entries):
                st.session_state["workspace-collection"] = collection
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
        if outcome.status == "FAILED":
            st.warning(
                "Analysis failed: "
                + plain(outcome.source_title or "Saved source")
                + ". The model could not complete this analysis. The original remains saved. "
                "Retry from its source details."
            )
        elif outcome.status == "IDLE":
            st.info("No pending source analysis for the current settings.")
        elif outcome.status == "SUCCEEDED":
            st.success("Analysis complete: " + plain(outcome.source_title or "Saved source"))
        if outcome.remaining_sources:
            noun = "source remains" if outcome.remaining_sources == 1 else "sources remain"
            st.caption(
                f"{outcome.remaining_sources} {noun} in the analysis queue. "
                "Queued work can include refreshing earlier analyses."
            )
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


def active_collection(work: Workspace) -> tuple[dict[UUID, str], UUID | None]:
    collections = dict(work.reads.collections(work.owner))
    # Retain the prior What Matters selection in an already open browser session.
    if "workspace-collection" not in st.session_state:
        st.session_state["workspace-collection"] = st.session_state.get("what-matters-scope")
    selected = st.session_state.get("workspace-collection")
    if selected not in collections:
        selected = None
        st.session_state["workspace-collection"] = None
    return collections, selected


def select_workspace_collection(key: str) -> None:
    st.session_state["workspace-collection"] = st.session_state[key]
    st.session_state.pop("ranking", None)


def collection_selector(work: Workspace, key: str) -> UUID | None:
    collections, selected = active_collection(work)
    st.session_state[key] = selected
    return st.selectbox(
        "Collection",
        [None, *collections],
        key=key,
        format_func=lambda value: collections[value] if value else "All sources",
        on_change=select_workspace_collection,
        args=(key,),
    )


def catch_up(work: Workspace) -> None:
    st.header("What Matters")
    collection = collection_selector(work, "what-matters-collection-picker")
    st.session_state.pop("feedback-notice", None)  # Retire the old off-screen page-level flash.
    interests = st.text_input(
        "What are you interested in right now? (optional)",
        placeholder="e.g. work software, travel plans, home renovation",
        help="This can help prioritize matching saved items. Leave it blank if you want "
        "LazyResearch to decide from your saved material.",
    )
    wanted = tuple(t.strip() for t in interests.split(",") if t.strip())
    scope = (work.owner, collection, wanted)
    if (
        st.button("Refresh What Matters", type="primary")
        or "ranking" not in st.session_state
        or st.session_state.get("ranking-scope") != scope
    ):
        with st.spinner("Finding what matters…"):
            st.session_state["ranking"] = work.catch_up(wanted, collection_id=collection)
            st.session_state["ranking-scope"] = scope
    decisions = st.session_state["ranking"]
    for column, (label, heading) in zip(st.columns(4), GROUPS.items(), strict=True):
        column.metric(heading, sum(d.label.value == label for d in decisions))
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
            message_key = f"feedback-message-{work.owner}-{decision.item.content_id}"
            refresh_key = f"feedback-refresh-{work.owner}-{decision.item.content_id}"
            with st.form(f"feedback-{decision.id}"):
                correction = st.selectbox(
                    "Your choice",
                    list(GROUPS),
                    format_func=lambda value: GROUPS[value],
                    index=list(GROUPS).index(label),
                )
                if message := st.session_state.get(message_key):
                    if message[0] == "success":
                        st.success(message[1])
                    else:
                        st.error(message[1])
                if refresh_message := st.session_state.get(refresh_key):
                    st.warning(refresh_message)
                if st.form_submit_button("Save feedback"):
                    st.session_state.pop(message_key, None)
                    st.session_state.pop(refresh_key, None)
                    key = f"feedback-event-{decision.item.content_id}"
                    try:
                        event = work.feedback(
                            decision,
                            Relevance(correction),
                            expected_event=st.session_state.get(key),
                        )
                    except RepositoryError as exc:
                        st.session_state[message_key] = (
                            "error",
                            "Could not save this choice. " + error_message(exc),
                        )
                    else:
                        # interact() has returned after its transaction committed. Set the
                        # acknowledgement before the independent projection refresh.
                        st.session_state[key] = event
                        st.session_state[message_key] = (
                            "success",
                            "Saved. LazyResearch will use this choice to learn your preferences.",
                        )
                        try:
                            updated = work.reviewed(
                                decision.item.content_id,
                                wanted,
                                collection_id=collection,
                            )
                        except RepositoryError:
                            st.session_state[refresh_key] = (
                                "Your choice was saved, but this view could not refresh. "
                                "Use Refresh What Matters to reload it."
                            )
                        else:
                            st.session_state["ranking"] = tuple(
                                updated if d.item.content_id == decision.item.content_id else d
                                for d in decisions
                                if updated or d.item.content_id != decision.item.content_id
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


def render_result(work: Workspace, result: Any, *, context: str = "history") -> None:
    st.caption(
        f"Published version {result.version} · research run {result.run_sequence} · "
        f"{result.published_at:%d %b %Y %H:%M %Z}"
    )
    if result.coverage == "PARTIAL":
        st.warning(
            "Partial coverage: this brief is available, but has limited coverage. "
            "Review the stored limitations below before relying on it."
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
        if not value and name not in {"answer", "summary", "findings", "recommendations"}:
            continue
        st.subheader(
            {"action_candidates": "Proposed actions", "claims": "Additional claims"}.get(
                name, name.capitalize()
            )
        )
        if not value:
            st.caption(f"This brief has no published {name}.")
            continue
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
                key=f"{context}-claim-{result.id}-{name}-{index}",
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
                key=f"{context}-conflict-{result.id}-{conflict_index}",
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
            if line == "insufficient_personal_sources":
                st.caption("There were too few saved sources for broad verification.")
            elif line == "selected_collection_context_used_without_question_match":
                st.caption(
                    "Evidence was sampled from your selected collection because no source "
                    "matched every word of the question. Relevance and completeness are limited."
                )
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


def select_research_scope() -> None:
    selected = st.session_state["research-collections-picker"]
    st.session_state["research-scope"] = selected
    active = selected[0] if len(selected) == 1 else None
    st.session_state["workspace-collection"] = active
    st.session_state["research-context"] = active
    st.session_state.pop("ranking", None)


def select_research_topic(scope: tuple[UUID, ...]) -> None:
    st.session_state.setdefault("research-topics-by-scope", {})[scope] = st.session_state[
        "research-topic-picker"
    ]
    st.session_state["research-topic-editor"] = False


def research(work: Workspace) -> None:
    st.header("Research")
    st.subheader("Start / Ask Research")
    collections, active = active_collection(work)
    if (
        "research-scope" not in st.session_state
        or st.session_state.get("research-context") != active
    ):
        st.session_state["research-scope"] = [active] if active else []
        st.session_state["research-context"] = active
        st.session_state["research-topic-editor"] = False
    st.session_state["research-collections-picker"] = [
        c for c in st.session_state["research-scope"] if c in collections
    ]
    selected_collections = st.multiselect(
        "Limit to collections (optional)",
        list(collections),
        key="research-collections-picker",
        format_func=lambda value: collections[value],
        on_change=select_research_scope,
    )
    scope = tuple(sorted(selected_collections))
    st.caption(
        "Collections choose saved sources. A research topic groups your questions and briefs."
    )
    with st.spinner("Opening your research…", show_time=True):
        topics_by_id = {t.id: t for t in work.reads.topics(work.owner)}
    choices = st.session_state.setdefault("research-topics-by-scope", {})
    selected_topic = choices.get(scope)
    st.session_state["research-topic-picker"] = (
        selected_topic if selected_topic in topics_by_id else None
    )
    topic_id = st.selectbox(
        "Research topic",
        [None, *topics_by_id],
        key="research-topic-picker",
        format_func=lambda identity: (
            topics_by_id[identity].title if identity else "Choose a topic…"
        ),
        on_change=select_research_topic,
        args=(scope,),
    )
    if st.button("+ New research topic"):
        st.session_state["research-topic-editor"] = True
    if topic_id is None or st.session_state.get("research-topic-editor"):
        if not topics_by_id:
            st.info("Create a topic for your first research question.")
        with st.form("new-topic"):
            title = st.text_input(
                "New topic name",
                value=collections[active] if active else "",
                placeholder="e.g. Project planning",
                key=f"research-new-topic-{scope}",
            )
            if st.form_submit_button("Create topic"):
                if not title.strip():
                    st.warning("Enter a topic name.")
                else:
                    created = work.mission_commands.create_topic(work.owner, title.strip())
                    choices[scope] = created.id
                    st.session_state["research-topic-editor"] = False
                    st.rerun()
    if topic_id is None:
        with st.expander("Previous research"):
            st.caption("Choose an existing research topic above to open its missions and briefs.")
        return
    topic = topics_by_id[topic_id]
    st.caption(
        "Research continues through the separate research worker, even when you leave this page. "
        "Requests are saved in PostgreSQL; refresh to read actual progress. "
        "Worker availability is not confirmed here. Use System status to check service access."
    )
    with st.form("mission"):
        question = st.text_area(
            "Research question",
            max_chars=500,
            placeholder="e.g. What are the main points, what changed, and what should I do next?",
        )
        public = st.checkbox("Allow current public web search", value=False)
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
    missions = work.reads.missions(work.owner, topic.id)
    # Preserve Current Brief policy when reruns fail or finish out of order.
    current = next(
        (m for m in missions if m.result_id and m.result_id == topic.current_result_id), None
    )
    st.subheader("Current research")
    if current:
        research_mission(work, current, current=True)
    else:
        st.info("No published brief yet. Research results appear here after publication.")
    pending = tuple(m for m in missions if m.status in {"QUEUED", "RUNNING"})
    if pending:
        st.subheader("Research in progress")
        for mission in pending:
            research_mission(work, mission)
    history_key = f"research-history-{topic.id}"
    panel = st.expander("Previous research", key=history_key, on_change="rerun")
    if panel.open:
        with panel:
            for mission in missions:
                if mission != current and mission not in pending:
                    research_mission(work, mission)
            research_history(work, topic)


def research_mission(work: Workspace, mission: MissionView, *, current: bool = False) -> None:
    st.markdown("**" + plain(mission.question) + "**")
    st.caption(f"Research run {mission.run_sequence}")
    st.write(mission_status(mission.status, mission.stage))
    if mission.status == "QUEUED":
        st.caption(
            "Waiting for the research service. If this stays queued, "
            "check the worker/server setup in README."
        )
    if mission.status == "FAILED":
        st.warning(
            "Research could not finish. Check the configured "
            "model/research services and try a new request. Your previous brief is retained."
        )
    if mission.status in {"QUEUED", "RUNNING"}:
        if st.button("Cancel research", key=f"cancel-{mission.id}"):
            work.cancel(mission.id)
            st.rerun()
    if mission.status not in {"COMPLETED", "PARTIAL"}:
        return
    if not mission.result_id:
        st.info("No published result is available for this mission.")
        return
    if mission.status == "PARTIAL":
        st.caption(
            "This result is based on limited evidence. Review the coverage limitations below."
        )
    open_key = f"research-open-{mission.id}"
    if not current and st.button("Open brief", key=f"view-result-{mission.id}"):
        st.session_state[open_key] = True
    if current or st.session_state.get(open_key):
        with st.spinner("Opening your brief…", show_time=True):
            result = work.reads.result(work.owner, mission.result_id)
        if result is None:
            st.info("This published result is no longer available.")
        else:
            render_result(work, result, context=f"mission-{mission.id}")


def research_history(work: Workspace, topic: Any) -> None:
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
    collection = collection_selector(work, "actions-collection-picker")
    if collection:
        st.caption(
            "Only actions whose cited sources all belong to this collection are shown. "
            "Actions with mixed or unassigned sources are available under All sources."
        )
    with st.spinner("Loading your actions…", show_time=True):
        items = work.actions(collection_id=collection)
    st.caption(f"{len(items)} actions")
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

NAVIGATION_SCROLL = """
<script>
(() => {
    if (window.lazyResearchNavigationScroll) {
        document.removeEventListener("click", window.lazyResearchNavigationScroll, true);
    }
    window.lazyResearchNavigationScroll = (event) => {
        const button = event.target.closest(".st-key-workspace-navigation button");
        if (!button || button.getAttribute("kind") === "primary") return;
        const main = document.querySelector('[data-testid="stMain"]');
        if (main) main.scrollTo({top: 0, left: 0, behavior: "instant"});
    };
    document.addEventListener("click", window.lazyResearchNavigationScroll, true);
})();
</script>
"""


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
        cached = st.session_state.get("workspace")
        if (
            cached is None
            or not callable(getattr(cached, "create_collection", None))
            or not callable(getattr(cached.reads, "create_collection", None))
        ):
            # A live development session can retain pre-collection class instances.
            # Replace only the composition object; keep form drafts and other UI state.
            st.session_state["workspace"] = build_workspace()
            logging.getLogger(__name__).warning(
                "workspace_recomposed collection_api=%s current_class_api=%s",
                callable(getattr(st.session_state["workspace"], "create_collection", None)),
                callable(getattr(Workspace, "create_collection", None)),
            )
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
    st.html(NAVIGATION_SCROLL, unsafe_allow_javascript=True)
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
