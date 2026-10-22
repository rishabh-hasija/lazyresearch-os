"""Synthetic Home Battery Systems fixtures. Fixtures only: no analyses, labels or results."""

from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.domain.content import SourceType

DEMO_REQUEST_KEY = "demo-home-battery-v1"


def _text(title: str, body: str) -> IntakeInput:
    return IntakeInput(
        source_type=SourceType.TEXT,
        title=title,
        payload=("SYNTHETIC DEMO FIXTURE. " + body).encode(),
    )


def home_battery_inputs() -> tuple[IntakeInput, ...]:
    return (
        _text(
            "My note: why a home battery",
            "Goal: use more of our rooftop solar in the evening. Budget ceiling EUR 8000. "
            "Ask two installers about 10 kWh systems and compare warranty years.",
        ),
        _text(
            "Installer A quote (10 kWh)",
            "Quote total EUR 6000 for a 10 kWh LFP battery, 10-year warranty. "
            "Please confirm the site assessment by 2026-11-07 to hold this price.",
        ),
        _text(
            "Installer B quote (10 kWh)",
            "Quote total EUR 6900 for a 10 kWh battery, 15-year warranty, installation "
            "included. Offer valid until 2026-11-20.",
        ),
        _text(
            "Article: how home batteries pay back",
            "Payback depends on the gap between grid price and feed-in tariff. At EUR 0.30 "
            "per kWh grid price and EUR 0.08 feed-in, a 10 kWh battery often needs 9 to 12 "
            "years to pay back. Compare usable capacity, not nameplate capacity.",
        ),
        _text(
            "Article: battery safety and fire codes",
            "Check that the installer is certified and that the installation location meets "
            "local fire-code distances. Ask for the datasheet and certification numbers.",
        ),
    )
