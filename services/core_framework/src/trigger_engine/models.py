from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class RuleCondition(BaseModel):
    """Defines a condition to be evaluated for a trigger rule."""
    # Example: Check a field in the event payload
    # More complex conditions (e.g., checking system state via State Manager API)
    # would require more elaborate structure or custom evaluation logic.
    field: str = Field(..., description="Path to the field in the event payload (e.g., 'payload.metadata.has_gps')")
    operator: str = Field(..., description="Comparison operator (e.g., '==', '!=', '>', '<', 'exists', 'not_exists')")
    value: Any = Field(None, description="Value to compare against (not required for 'exists'/'not_exists')")

class RuleAction(BaseModel):
    """Defines an action to be taken if a rule's conditions are met."""
    action_type: str = Field(..., description="Type of action (e.g., 'publish_event')")
    target_event_type: Optional[str] = Field(None, description="Event type to publish if action_type is 'publish_event'")
    payload_override: Optional[Dict[str, Any]] = Field(None, description="Optional payload modifications or additions for the published event")
    # Could add other action types like 'call_api'

class TriggerRule(BaseModel):
    """Defines a rule for the Trigger Evaluation Engine."""
    rule_id: str = Field(..., description="Unique identifier for the rule")
    description: Optional[str] = Field(None, description="Human-readable description of the rule")
    trigger_event_types: List[str] = Field(..., description="List of event types that can initiate this rule's evaluation")
    conditions: List[RuleCondition] = Field(..., description="List of conditions (AND logic) that must be met")
    actions: List[RuleAction] = Field(..., description="List of actions to perform if conditions are met")
    enabled: bool = Field(default=True, description="Whether the rule is currently active")

