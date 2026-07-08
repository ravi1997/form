"""Resources API blueprint — thin facade.

All route handlers have been extracted into focused modules:
  - resources_support.py   : blueprint, hooks, _error helper
  - resources_context.py   : shared resolvers and update helpers
  - resources_utils.py     : RBAC, pagination, actions, security
  - resources_schemas.py   : path/query/response schema models
  - resources_projects.py  : project CRUD + versions
  - resources_forms.py     : form CRUD + versions + workflow + UI config
  - resources_sections.py  : section CRUD + versions
  - resources_questions.py : question CRUD + versions
  - resources_choices.py   : choice CRUD
  - resources_actions.py   : action trigger + execution list
"""
from __future__ import annotations

# Import blueprint first so before/after_request hooks are registered.
from app.api.resources_support import resources_api  # noqa: F401

# Import route modules so their decorators register routes on resources_api.
from app.api import (  # noqa: F401
    resources_projects,
    resources_forms,
    resources_sections,
    resources_questions,
    resources_choices,
    resources_actions,
)

__all__ = ["resources_api"]
