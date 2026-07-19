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

class Status(str, Enum):
    to_read = "to-read"
    reading = "reading"
    read = "read"
    abandoned = "abandoned"

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
    member_of = "member_of"

class Edge(BaseModel):
    type: EdgeType
    to: str = Field(description="slug or [[wikilink]] target of an existing or new node")
    note: Optional[str] = None

class NodeRef(BaseModel):
    type: NodeType
    slug: str = Field(description="kebab-case stable id, e.g. 'reAct')")
    title: str
    status: Optional[Status] = Field(
        default=None,
        description="lifecycle status for paper/book/article nodes only. to-read | reading | read | abandoned. Omit for other node types.",
    )
    summary: Optional[str] = None
    attributes: dict[str, str | list[str]] = Field(default_factory=dict)

class IngestResult(BaseModel):
    node: NodeRef
    action: Literal["create", "update"] = Field(
        default="create",
        description="create = new node file. update = merge into existing node file (matched from candidates list). If slug collides with an existing file the writer will treat it as update regardless.",
    )
    edges: list[Edge] = Field(default_factory=list)
    spawn: list[NodeRef] = Field(
        default_factory=list,
        description="new related nodes the agent wants created (concepts, people, projects). Ignored on update for the matched node itself, but spawned if not already present.",
    )
    body_markdown: str = Field(default="", description="markdown body for the note, in the user's voice, no frontmatter")

def validate(payload: dict) -> IngestResult:
    return IngestResult.model_validate(payload)

class SchemaError(Exception):
    def __init__(self, err: ValidationError):
        self.err = err
        super().__init__(err.error_count())