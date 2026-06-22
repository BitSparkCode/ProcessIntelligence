"""AI-driven conformance & deviation explanation (Story 6.2).

Turns a structured :class:`ConformanceReport` into a concise natural-language
summary a process owner can act on. Uses the LLM when configured; otherwise a
deterministic template so the feature always works (and CI stays offline).
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.schemas.analysis import ConformanceReport
from app.services.ai.llm import LLMClient, get_llm_client


def explain_deviations(
    report: ConformanceReport,
    *,
    settings: Settings | None = None,
    client: LLMClient | None = None,
) -> tuple[str, str]:
    """Return ``(explanation_text, source)`` where source is 'ai' or 'heuristic'."""
    settings = settings or get_settings()
    client = client or get_llm_client(settings)

    if client.enabled:
        try:
            return _explain_with_llm(report, client), "ai"
        except Exception:  # noqa: BLE001 - any failure falls back safely
            return _explain_heuristic(report), "heuristic"
    return _explain_heuristic(report), "heuristic"


def _facts(report: ConformanceReport) -> str:
    top = report.deviation_summary[:8]
    lines = [
        f"Cases checked: {report.case_count}",
        f"Fully conforming cases: {report.fitting_case_count} "
        f"({report.percentage_fitting:.0f}%)",
        f"Overall fitness: {report.fitness:.2f} (1.0 = perfect)",
        "Most frequent deviations:",
    ]
    if top:
        for d in top:
            lines.append(f"- {d.description} (in {d.case_count} cases)")
    else:
        lines.append("- none; the log fully matches the reference model")
    return "\n".join(lines)


def _explain_with_llm(report: ConformanceReport, client: LLMClient) -> str:
    system = (
        "You are a process-mining analyst. Explain conformance-checking results "
        "to a business process owner in clear, concise language. Summarize how "
        "well reality matches the target process, call out the most important "
        "deviations and what they imply, and suggest where to look. "
        "3-5 short sentences, no markdown, no preamble."
    )
    user = f"Conformance results:\n{_facts(report)}"
    return client.complete(system=system, user=user).text.strip()


def _explain_heuristic(report: ConformanceReport) -> str:
    if report.case_count == 0:
        return "The log has no cases to compare against the reference model."

    parts: list[str] = []
    pct = report.percentage_fitting
    quality = (
        "closely follows" if pct >= 80 else "partially follows" if pct >= 40 else "diverges from"
    )
    parts.append(
        f"The process {quality} the reference model: "
        f"{report.fitting_case_count} of {report.case_count} cases "
        f"({pct:.0f}%) conform exactly, with an overall fitness of "
        f"{report.fitness:.2f}."
    )

    if not report.deviation_summary:
        parts.append("No deviations were found.")
        return " ".join(parts)

    top = report.deviation_summary[:3]
    desc = "; ".join(f"{d.description.lower()} ({d.case_count} cases)" for d in top)
    parts.append(f"The most frequent deviations are: {desc}.")

    missing = [d for d in report.deviation_summary if d.kind == "missing"]
    unexpected = [d for d in report.deviation_summary if d.kind == "unexpected"]
    order = [d for d in report.deviation_summary if d.kind == "order"]
    hints: list[str] = []
    if missing:
        hints.append("steps defined in the model are being skipped")
    if unexpected:
        hints.append("activities are performed that the model does not allow")
    if order:
        hints.append("some activities run out of the prescribed order")
    if hints:
        parts.append("This indicates that " + ", and ".join(hints) + ".")
    return " ".join(parts)
