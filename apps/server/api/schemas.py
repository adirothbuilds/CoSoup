from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MovementRequest(Input):
    scope: Literal["portfolio", "candidates", "near_breakouts"]
    portfolio_id: str | None = None
    report_id: str | None = None
    data_date: date | None = None
    period: Literal["1D", "1W", "1M"] = "1D"


class ScanRequest(Input):
    mode: Literal["live", "historical_snapshot"] = "live"
    start_date: date | None = None
    end_date: date | None = None
    rules_id: str | None = None
    acquisition: Literal["missing_only"] = "missing_only"
    research: Literal["none", "current", "as_of_only"] = "none"
    offline: bool = False

    @model_validator(mode="after")
    def dates(self):
        if self.offline and self.research != "none":
            raise ValueError("Company research requires online sources; disable offline or select research=none")
        if bool(self.start_date) != bool(self.end_date):
            raise ValueError("Provide both range dates or neither")
        if self.mode == "historical_snapshot" and self.research == "current":
            raise ValueError("Historical snapshots cannot use current research")
        if self.mode == "live" and self.research == "as_of_only":
            raise ValueError("as_of_only research belongs to historical snapshots")
        return self


class WeeklyRequest(Input):
    end_date: date | None = None
    mode: Literal["live", "historical_snapshot"] = "live"


class ScheduleRequest(Input):
    name: str = Field(min_length=1, max_length=120)
    trigger: dict
    task: dict
    missed_run_policy: Literal["skip", "run_once", "catch_up"] = "run_once"
    enabled: bool = True


class PortfolioRequest(Input):
    name: str = Field(min_length=1, max_length=120)
    currency: Literal["USD"] = "USD"


class TransactionRequest(Input):
    type: Literal["buy", "sell", "opening", "deposit", "withdrawal", "dividend", "fee", "split"]
    at: datetime
    symbol: str | None = Field(None, pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,29}$")
    quantity: Decimal | None = Field(None, gt=0, max_digits=28, decimal_places=10)
    price: Decimal | None = Field(None, ge=0, max_digits=28, decimal_places=10)
    amount: Decimal | None = Field(None, gt=0, max_digits=28, decimal_places=10)
    fees: Decimal = Field(Decimal("0"), ge=0, max_digits=28, decimal_places=10)
    currency: Literal["USD"] = "USD"
    external_ref: str | None = Field(None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def fields(self):
        if self.at.tzinfo is None:
            raise ValueError("Transaction timestamp must include a timezone")
        if self.type in {"buy", "sell", "opening", "split"}:
            if not self.symbol or self.quantity is None or self.amount is not None:
                raise ValueError("Share transaction needs symbol/quantity and no cash amount")
            if self.type in {"buy", "sell"} and (self.price is None or self.price <= 0):
                raise ValueError("Buy/sell requires a positive actual price")
            if self.type == "split" and (self.price is not None or self.fees):
                raise ValueError("Split uses quantity as factor; no price or fees")
        elif self.amount is None or self.quantity is not None or self.price is not None or self.symbol is not None:
            raise ValueError("Cash transaction needs amount and no share fields")
        return self


class AnalysisRequest(Input):
    data_date: date | None = None


class ImportRequest(Input):
    upload_id: str
    portfolio_id: str


class ConfirmImport(Input):
    # All entries are explicitly reviewed/edited by the owner, not applied by OCR.
    rows: list[TransactionRequest] = Field(min_length=1, max_length=500)


class RestoreRequest(Input):
    artifact_ids: list[str] = Field(min_length=1, max_length=100)


class AgentRequest(Input):
    profile_id: Literal["research-analyst"] = "research-analyst"
    task_type: Literal["daily_review", "weekly_review", "portfolio_review", "document_review"]
    prompt: str = Field(min_length=1, max_length=8000)
    start_date: date | None = None
    end_date: date | None = None
    report_ids: list[str] = Field(default_factory=list, max_length=30)
    portfolio_id: str | None = None
    allow_portfolio_data: bool = False
    upload_ids: list[str] = Field(default_factory=list, max_length=4)
    allow_uploaded_documents: bool = False
    allow_current_web_research: Literal[False] = False

    @model_validator(mode="after")
    def scope(self):
        if self.upload_ids and not self.allow_uploaded_documents:
            raise ValueError("Uploaded document export needs explicit permission")
        if self.task_type == "document_review" and not self.upload_ids:
            raise ValueError("Document review requires an authorized image")
        if self.task_type == "portfolio_review" and (not self.portfolio_id or not self.allow_portfolio_data):
            raise ValueError("Portfolio review needs an explicit portfolio and data-export permission")
        if self.portfolio_id and not self.allow_portfolio_data:
            raise ValueError("Portfolio data was not authorized")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Invalid task range")
        return self
