import json

import enquest_config as config


def load_taxonomy():
    with open(config.TAXONOMY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def hazard_labels(taxonomy):
    return [l["label"] for l in taxonomy["hazard"]["labels"]]


def human_factors_labels(taxonomy):
    return [l["label"] for l in taxonomy["human_factors"]["labels"]]


def _format_label_table(labels):
    lines = []
    for l in labels:
        lines.append(f"- {l['label']}\n  Keyword triggers: {l['keyword_triggers']}\n  Guidance: {l['guidance']}")
    return "\n".join(lines)


def build_agent_instructions(taxonomy):
    """Builds the text that must be pasted into the Foundry portal's Agent
    "Instructions" field. This project's agent type does not accept an
    `instructions` (or `text`/response_format) override per API call --
    "Not allowed when agent is specified" -- so the portal-configured
    instructions are the only place this can live. Re-run this (via
    enquest_agent_setup.py) and re-paste into the portal whenever
    enquest_taxonomy.json changes.

    Since structured-output JSON schema enforcement also can't be sent
    per-call, the required output shape is spelled out explicitly here
    instead, and the client parses leniently (see
    EnquestClassifierClient._parse_response).
    """
    hazard = taxonomy["hazard"]
    hf = taxonomy["human_factors"]

    hazard_rules = "\n".join(f"{i+1}. {r}" for i, r in enumerate(hazard["precedence_rules"]))
    hf_rules = "\n".join(f"{i+1}. {r}" for i, r in enumerate(hf["precedence_rules"]))
    design_principles = "\n".join(f"- {p}" for p in taxonomy.get("design_principles", []))

    return f"""You are an intelligent assistant that classifies safety observation cards (BBSS cards) from an offshore oil & gas operator on two independent dimensions: Hazard and Human Factors. You reason from the definitions, precedence rules, and guidance below -- the keyword triggers are seeding material to suggest relevance, not a lookup table to match literally.

For every message you receive, the message is the free text of one observation card. Classify that single card.

DESIGN PRINCIPLES
{design_principles}

=== HAZARD DIMENSION ===
Assign exactly one label from:
{", ".join(hazard_labels(taxonomy))}

Hazard precedence rules, applied in this order when text could support more than one label:
{hazard_rules}

Hazard label library:
{_format_label_table(hazard["labels"])}

=== HUMAN FACTORS DIMENSION ===
Assign exactly one label from:
{", ".join(human_factors_labels(taxonomy))}

Human Factors precedence rules, applied in this order when text could support more than one label:
{hf_rules}

Human Factors label library:
{_format_label_table(hf["labels"])}

Confidence definitions: High = explicit trigger and unambiguous fit; Medium = inferred from context without an explicit trigger; Low = weak or conflicting evidence.

=== OUTPUT FORMAT ===
Respond with ONLY a JSON object, no other text, no markdown code fences, in exactly this shape:
{{
  "hazard": {{"label": "<one label from the Hazard list above>", "confidence": "High|Medium|Low"}},
  "human_factors": {{"label": "<one label from the Human Factors list above>", "confidence": "High|Medium|Low"}}
}}
"""


def build_response_json_schema(taxonomy):
    """JSON schema describing the required output shape. NOT sent/enforced
    per API call for this agent type (the `text` param is rejected once an
    agent is specified) -- kept here only in case the Foundry portal's own
    Agent configuration UI offers a place to set structured-output
    enforcement, and printed for reference by enquest_agent_setup.py.
    Actual enforcement is via the OUTPUT FORMAT section of
    build_agent_instructions() plus lenient client-side parsing."""
    return {
        "type": "object",
        "properties": {
            "hazard": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "enum": hazard_labels(taxonomy)},
                    "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
                },
                "required": ["label", "confidence"],
                "additionalProperties": False,
            },
            "human_factors": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "enum": human_factors_labels(taxonomy)},
                    "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
                },
                "required": ["label", "confidence"],
                "additionalProperties": False,
            },
        },
        "required": ["hazard", "human_factors"],
        "additionalProperties": False,
    }


def build_observation_text(hazard_description, action_taken):
    # Same construction as the sibling "Not Applicable" mis-tagging classifier:
    # Hazard_Description + " " + Action_Taken.
    return f"{hazard_description or ''} {action_taken or ''}".strip()
