# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""Configuration schema of search categories in SearXNG
"""

from typing import List

from pydantic import (
    BaseModel,
    Field,
    validator,
)
from pydantic_yaml import YamlModel

class SearchCategory(BaseModel):
    """Schema of a search category in SearXNG."""

    id: str
    """ID of the category, the ID of a category is used in SearXNG templates, APIs
    and other code related topics."""

    ui_tab: bool = False
    """Category is (or is not) shown as tab in the UI."""

    name_en: str
    """Name (EN) of the category, the name of the category is used in the UI and is
    a part of the translation workflow."""


class CategoryConfig(YamlModel):
    """Configuration of the categories in SearXNG
    """

    categories: List[SearchCategory]
    """The list of categories in SearXNG."""

    class Config:
        min_version = "1.0.0"
        max_version = "1.0.0"
