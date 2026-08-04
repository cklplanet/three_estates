import unittest
from pathlib import Path


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
    / "three_estates_sim"
    / "backend_server"
)


class UnifiedBiddingPromptTests(unittest.TestCase):
    def test_static_template_does_not_advertise_unavailable_actions(self):
        template = (
            BACKEND_ROOT
            / "persona"
            / "prompt_template"
            / "templates"
            / "reaction_bidding_unified.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("{action_options}", template)
        self.assertIn("actions absent from this list are unavailable", template)
        for static_rule in (
            "- speak:",
            "- reveal:",
            "- nun-reveal:",
            "- ability:",
            "- retrieve:",
        ):
            self.assertNotIn(static_rule, template)

    def test_dynamic_builder_has_rules_for_every_action_type(self):
        runner = (
            BACKEND_ROOT
            / "persona"
            / "prompt_template"
            / "run_gpt_prompt.py"
        ).read_text(encoding="utf-8")
        for action in (
            '"none"',
            '"speak"',
            '"reveal"',
            '"nun-reveal"',
            '"ability"',
            '"retrieve"',
        ):
            self.assertIn(action, runner)
        self.assertIn("for option in action_options", runner)

    def test_innkeeper_is_explicit_solo_ability_exception(self):
        planner = (
            BACKEND_ROOT / "persona" / "cognitive_modules" / "plan.py"
        ).read_text(encoding="utf-8")
        self.assertIn('if table_size <= 1 and role != "Innkeeper":', planner)


if __name__ == "__main__":
    unittest.main()
