from typing import Literal

from pydantic import BaseModel

Severity = Literal["critical", "high", "medium", "low"]
DecisionKind = Literal["approve", "approve_edited", "dismiss"]


class EvidencePoint(BaseModel):
    label: str
    value: str
    bad: bool


class FixOut(BaseModel):
    kind: Literal["message", "content"]
    recipient: Literal["brand", "internal"]
    source: Literal["rule", "ai"]
    text: str | None = None
    title: str | None = None
    title_note: str | None = None
    bullets: list[str] = []


class IssueOut(BaseModel):
    id: int
    rule_id: str
    sku: str
    platform: str
    brand: str
    brand_slug: str
    issue_code: str
    issue_label: str
    severity: Severity
    impact_inr: float
    impact_calc_text: str
    evidence: dict
    evidence_points: list[EvidencePoint]
    fix: FixOut
    suggested_fix: str
    ai_generated: bool
    recipient: Literal["brand", "internal"]
    status: Literal["open", "approved", "dismissed"]
    detected_at: str
    decided_at: str | None = None


class SnapshotOut(BaseModel):
    id: int
    status: Literal["uploaded", "audited"]
    uploaded_at: str
    audited_at: str | None
    row_counts: dict[str, int]


class PortfolioCell(BaseModel):
    brand: str
    brand_slug: str
    category: str
    platform: str
    listing_count: int
    issue_count: int
    severity_counts: dict[str, int]
    capped_daily_loss_inr: float


class PortfolioOut(BaseModel):
    snapshot: SnapshotOut | None
    brands: list[str]
    platforms: list[str]
    cells: list[PortfolioCell]
    total_daily_loss_inr: float
    uncapped_daily_loss_inr: float
    severity_counts: dict[str, int]
    oldest_open_at: dict[str, str | None]
    open_issue_count: int
    flagged_listing_count: int
    listing_count: int
    approved_count: int
    dismissed_count: int
    approved_impact_inr: float
    has_data: bool
    ai_enabled: bool
    ai_available: bool


class ListingSnapshotOut(BaseModel):
    snapshot_date: str
    title: str
    price: float
    mrp: float
    stock: float
    rating: float
    review_count: int
    status: str
    buybox_owner: str
    image_count: int
    bullet_count: int


class SnapshotRow(BaseModel):
    field: str
    label: str
    previous: str | None
    latest: str
    change: str | None
    tone: Literal["bad", "chg", "same"]


class PlatformDetailOut(BaseModel):
    platform: str
    buybox_label: str
    latest: ListingSnapshotOut
    previous: ListingSnapshotOut | None
    deltas: dict[str, float]
    snapshot_rows: list[SnapshotRow]
    issues: list[IssueOut]


class ReviewOut(BaseModel):
    platform: str
    review_date: str
    stars: int
    text: str
    language: Literal["en", "hinglish"]
    translation: str | None = None


class ComplaintThemeOut(BaseModel):
    theme: str
    polarity: Literal["neg", "pos"]
    count: int
    example_quote: str


class SkuDetailOut(BaseModel):
    sku: str
    brand: str
    brand_slug: str
    category: str
    platforms: dict[str, PlatformDetailOut]
    missing_platforms: list[str]
    reviews: list[ReviewOut]
    representative_reviews: list[ReviewOut]
    star_distribution: dict[str, int]
    average_stars: float | None
    complaint_themes: list[ComplaintThemeOut]
    themes_ai_generated: bool
    ai_enabled: bool


class BrandReportOut(BaseModel):
    brand: str
    brand_slug: str
    category: str
    listing_count: int
    audited_at: str | None
    week_start: str
    week_end: str
    prev_week: str | None
    next_week: str | None
    has_data: bool
    summary: str
    ai_generated: bool
    total_issues: int
    open_issues: int
    total_impact_inr: float
    critical_count: int
    approved_count: int
    dismissed_count: int
    top_issues: list[IssueOut]


class DecisionIn(BaseModel):
    issue_id: int
    decision: DecisionKind
    fix_text: str | None = None


class DecisionOut(BaseModel):
    id: int
    issue_id: int
    decision: DecisionKind
    recipient: Literal["brand", "internal"]
    final_text: str | None
    decided_at: str
    undone_at: str | None
    sku: str
    platform: str
    brand: str
    issue_code: str
    issue_label: str
    impact_inr: float


class UploadResultOut(BaseModel):
    listings: int
    ads: int
    reviews: int
    snapshot: SnapshotOut


class AuditResultOut(BaseModel):
    issues_computed: int
    snapshot: SnapshotOut


class AiSettingIn(BaseModel):
    enabled: bool


class AiSettingOut(BaseModel):
    enabled: bool
    available: bool
    updated_count: int = 0
