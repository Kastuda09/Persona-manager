"""
Content Engine Prototype - Station 1, 2 (AI-powered), and 4
This is the "heart" of the platform: takes a persona + a trigger (news,
idea, or comment theme) and produces a ready-to-approve post.

To actually run this yourself later, you'd need your own Anthropic API key
set as an environment variable (ANTHROPIC_API_KEY). Right now this file is
built and structured so it's ready to plug that in.
"""

import os
import json
from datetime import datetime, timedelta

try:
    import anthropic
    CLIENT_AVAILABLE = True
except ImportError:
    CLIENT_AVAILABLE = False


class Persona:
    def __init__(self, name, niche, tone, rules):
        self.name = name
        self.niche = niche
        self.tone = tone
        self.rules = rules  # e.g. "no financial advice, ask a question at the end"


class ContentEngine:
    def __init__(self, persona, api_key=None):
        self.persona = persona
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = None
        if CLIENT_AVAILABLE and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)

    def station1_collect_input(self, trigger_type, trigger_content):
        return {
            "persona": self.persona.name,
            "niche": self.persona.niche,
            "tone": self.persona.tone,
            "rules": self.persona.rules,
            "trigger_type": trigger_type,
            "trigger_content": trigger_content,
        }

    def station2_write(self, collected_input):
        if not self.client:
            return self._station2_fallback_template(collected_input)

        system_prompt = (
            f"You are writing social media content in the voice of a persona named "
            f"{collected_input['persona']}, focused on {collected_input['niche']}. "
            f"Tone: {collected_input['tone']}. Rules you must follow: {collected_input['rules']}. "
            f"Output ONLY valid JSON with keys: hook, body, closing_question, hashtags "
            f"(a list of 3-5 short hashtags), flagged_for_review (boolean, true if the "
            f"content edges into financial/medical/legal advice and needs human review)."
        )
        user_prompt = f"Trigger ({collected_input['trigger_type']}): {collected_input['trigger_content']}"

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = message.content[0].text.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return self._station2_fallback_template(collected_input)

    def _station2_fallback_template(self, collected_input):
        headline = collected_input["trigger_content"]
        return {
            "hook": f"Everyone's talking about: {headline}. Here's what's really going on.",
            "body": f"In {collected_input['niche']} terms, this matters because it signals "
                    f"a shift in how people are positioning. Not advice, just what the data shows.",
            "closing_question": "What do you think this really means? Drop your take below.",
            "hashtags": ["#markets", "#macro", "#" + collected_input["niche"].replace(" ", "")],
            "flagged_for_review": False,
        }

    def station4_package(self, draft):
        best_time = (datetime.now() + timedelta(hours=6)).strftime("%A %I:%M %p")
        return {
            "caption": f"{draft['hook']} {draft['body']} {draft['closing_question']}",
            "hashtags": draft["hashtags"],
            "suggested_post_time": best_time,
            "flagged_for_review": draft.get("flagged_for_review", False),
            "status": "awaiting_approval",
        }

    def run(self, trigger_type, trigger_content):
        collected = self.station1_collect_input(trigger_type, trigger_content)
        draft = self.station2_write(collected)
        return self.station4_package(draft)


if __name__ == "__main__":
    adrian = Persona(
        name="Adrian Cole",
        niche="trading",
        tone="sharp, witty, non-advisory",
        rules="no buy or sell signals, always end with a question, never claim certainty about future prices",
    )

    engine = ContentEngine(adrian)  # will use fallback template if no API key is set
    result = engine.run(
        trigger_type="headline",
        trigger_content="Bitcoin surges past $77,000 while gold hits record highs",
    )
    print(json.dumps(result, indent=2))
