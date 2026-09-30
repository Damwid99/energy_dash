from typing import Literal

from pydantic import BaseModel, Field

Horizon = Literal["short", "long"]


class SelectedArticle(BaseModel):
    id: int = Field(description="Numer artykułu z listy wejściowej")
    horizon: Horizon = Field(description="short = dziś i najbliższe dni, long = tygodnie/miesiące")


class Selection(BaseModel):
    selected: list[SelectedArticle]


class DigestItem(BaseModel):
    horizon: Horizon
    commodity: Literal["power", "gas", "oil", "co2", "general"]
    impact: Literal["up", "down", "neutral", "unclear"] = Field(
        description="Kierunek wpływu na ceny energii elektrycznej w Polsce"
    )
    summary: str = Field(description="1-2 zdania po polsku: co się stało i dlaczego to ważne")
    source_ids: list[int] = Field(description="Numery artykułów, na których opiera się punkt")


class Digest(BaseModel):
    items: list[DigestItem]
