# me-kg schema: fixed vocabularies enforced by pydantic.
# Changing this file is the only way to introduce new node/edge types.

from __future__ import annotations
from enum import Enum
from typing import Literal, Optional
from datetime import date
from pydantic import BaseModel, Field, ValidationError

class NodeType(str, Enum):
    paper = "paper"
    project = "project"
    note = "note"
    idea = "idea"
    book = "book"
    article = "article"
    person = "person"
    concept = "concept"
    tag = "tag"

class EdgeType(str, Enum):
    cites = "cites"
    extends = "extends"
    relates_to_concept = "relates_to_concept"
    uses = "uses"
    implements = "implements"
    author_of = "author_of"
    part_of = "part_of"
    idea_from = "idea_from"
    discusses = "discusses"
    mentions_person = "mentions_person"
    tagged = "tagged"
    depends_on = "depends_on"
    built_with = "built_with"

class Edge(BaseModel):
    type: EdgeType
    to: str = Field(description="slug or [[wikilink]] target of an existing or new node")
    note: Optional[str] = None

class NodeRef(BaseModel):
    type: NodeType
    slug: str = Field(description="kebab-case stable id, e.g. 'reAct')")
    title: str
    summary: Optional[str] = None
    attributes: dict[str, str | list[str]] = Field(default_factory=dict)

class IngestResult(BaseModel):
    node: NodeRef
    edges: list[Edge] = Field(default_factory=list)
    spawn: list[NodeRef] = Field(
        default_factory=list,
        description="new related nodes the agent wants created (concepts, people, projects)",
    )
    body_markdown: str = Field(default="", description="markdown body for the note, in the user's voice, no frontmatter")

def validate(payload: dict) -> IngestResult:
    return IngestResult.model_validate(payload)

class SchemaError(Exception):
    def __init__(self, err: ValidationError):
        self.err = err
        super().__init__(err.error_count())