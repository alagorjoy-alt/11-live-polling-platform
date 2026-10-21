"""Request validation models."""
from pydantic import BaseModel, Field, field_validator


class PollCreate(BaseModel):
    question: str = Field(min_length=3, max_length=200)
    options: list[str] = Field(min_length=2, max_length=10)
    duration_minutes: int | None = Field(default=None, ge=1, le=10080)  # up to 7 days

    @field_validator("question")
    @classmethod
    def clean_question(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("Question must be at least 3 characters")
        return v

    @field_validator("options")
    @classmethod
    def clean_options(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(v.split()) for v in values]
        if any(not v for v in cleaned):
            raise ValueError("Options cannot be empty")
        if any(len(v) > 100 for v in cleaned):
            raise ValueError("Each option must be 100 characters or fewer")
        if len({v.lower() for v in cleaned}) != len(cleaned):
            raise ValueError("Options must be unique")
        return cleaned


class VoteIn(BaseModel):
    option_id: int = Field(gt=0)
