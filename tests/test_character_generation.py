import sys
import re
import unittest
from pathlib import Path


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
    / "three_estates_sim"
    / "backend_server"
)
sys.path.insert(0, str(BACKEND_ROOT))

from character_generation import normalize_character_name_roster


class CharacterRosterTests(unittest.TestCase):
    def test_name_prompt_keeps_established_formatting_examples(self):
        prompt = (
            BACKEND_ROOT
            / "persona"
            / "prompt_template"
            / "templates"
            / "generate_character_names.txt"
        ).read_text(encoding="utf-8")
        for example in (
            "Artoria 'Saber' Pendragon",
            "Aoi 'Hina' Asahina",
            "Enciodes 'SilverAsh' Silverash",
            "'Exusiai' Lemuel",
            "Amiya",
            "Gilgamesh",
        ):
            self.assertIn(example, prompt)

    def test_chinese_name_prompt_uses_localized_examples(self):
        prompt = (
            BACKEND_ROOT
            / "locales"
            / "zh-CN"
            / "prompts"
            / "generate_character_names.txt"
        ).read_text(encoding="utf-8")
        for example in (
            "“Saber”阿尔托莉雅·潘德拉贡",
            "朝日奈葵",
            "“银灰”恩希欧迪斯·希瓦艾什",
            "“能天使”蕾缪乐",
            "阿米娅",
            "吉尔伽美什",
        ):
            self.assertIn(example, prompt)
        self.assertIn("阿库娅与惠惠", prompt)
        self.assertNotIn("Aoi 'Hina' Asahina", prompt)

    def test_chinese_character_generation_suite_has_native_overrides(self):
        prompts_dir = BACKEND_ROOT / "locales" / "zh-CN" / "prompts"
        expected = {
            "generate_character_names.txt",
            "generate_persona.txt",
            "generate_innate_appearance.txt",
            "generate_clothing.txt",
            "assign_immersion_roles.txt",
            "select_relationship_pairs.txt",
            "generate_relationship.txt",
        }
        self.assertTrue(expected.issubset({path.name for path in prompts_dir.iterdir()}))

    def test_japanese_name_prompt_uses_localized_nickname_conventions(self):
        prompt = (
            BACKEND_ROOT
            / "locales"
            / "ja-JP"
            / "prompts"
            / "generate_character_names.txt"
        ).read_text(encoding="utf-8")
        for example in (
            "アルトリア・ペンドラゴン（セイバー）",
            "相沢 智（トモ）",
            "久保田 淳一郎（ジュン）",
            "ヘンリー・R・シュレイダー（ハンク）",
            "エンヤ・シルバーアッシュ（プラマニクス）",
            "レミュエル（エクシア）",
            "朝日奈 葵",
            "アーミヤ",
            "ギルガメッシュ",
        ):
            self.assertIn(example, prompt)
        self.assertIn("アクアとめぐみん", prompt)

    def test_japanese_prompt_suite_matches_chinese_overrides(self):
        chinese = {
            path.name
            for path in (BACKEND_ROOT / "locales" / "zh-CN" / "prompts").iterdir()
        }
        japanese = {
            path.name
            for path in (BACKEND_ROOT / "locales" / "ja-JP" / "prompts").iterdir()
        }
        self.assertEqual(japanese, chinese)
        placeholder_pattern = re.compile(
            r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})"
        )
        for filename in chinese:
            chinese_text = (
                BACKEND_ROOT / "locales" / "zh-CN" / "prompts" / filename
            ).read_text(encoding="utf-8")
            japanese_text = (
                BACKEND_ROOT / "locales" / "ja-JP" / "prompts" / filename
            ).read_text(encoding="utf-8")
            self.assertEqual(
                set(placeholder_pattern.findall(japanese_text)),
                set(placeholder_pattern.findall(chinese_text)),
                filename,
            )

    def test_japanese_fixed_character_budgets_are_1_2x_chinese(self):
        prompts_dir = BACKEND_ROOT / "locales" / "ja-JP" / "prompts"
        self.assertIn(
            "96文字未満",
            (prompts_dir / "generate_innate_appearance.txt").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            "84文字未満",
            (prompts_dir / "generate_clothing.txt").read_text(encoding="utf-8"),
        )
        for filename in (
            "generate_next_convo_line_normal.txt",
            "generate_next_convo_line_special.txt",
            "bishop_wrong_guess_response.txt",
            "spinster_endgame_guess.txt",
        ):
            self.assertIn(
                "72文字",
                (prompts_dir / filename).read_text(encoding="utf-8"),
                filename,
            )

    def test_chinese_narrative_budgets_use_character_equivalents(self):
        prompts_dir = BACKEND_ROOT / "locales" / "zh-CN" / "prompts"
        persona_prompt = (prompts_dir / "generate_persona.txt").read_text(
            encoding="utf-8"
        )
        relationship_prompt = (
            prompts_dir / "generate_relationship.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("{innate_profile_limit}", persona_prompt)
        self.assertIn("{relationship_limit}", relationship_prompt)

    def test_persona_prompts_exclude_temporary_game_scenario_facts(self):
        prompt_paths = {
            "en": (
                BACKEND_ROOT
                / "persona"
                / "prompt_template"
                / "templates"
                / "generate_persona.txt"
            ),
            "zh": BACKEND_ROOT / "locales" / "zh-CN" / "prompts" / "generate_persona.txt",
            "ja": BACKEND_ROOT / "locales" / "ja-JP" / "prompts" / "generate_persona.txt",
        }
        expected_rules = {
            "en": ("personal history", "social-deduction game", "temporary scenario"),
            "zh": ("个人经历", "社交推理游戏", "临时场景"),
            "ja": ("個人的な来歴", "社会的推理ゲーム", "一時的なシナリオ"),
        }
        for locale, path in prompt_paths.items():
            prompt = path.read_text(encoding="utf-8")
            for rule in expected_rules[locale]:
                self.assertIn(rule, prompt, f"{locale}: {rule}")

    def test_preserves_supplied_order_and_spelling(self):
        result = normalize_character_name_roster(
            {"names": ["Peko Pekoyama", "Nagito Komaeda", "Chiaki Nanami"]},
            3,
        )
        self.assertEqual(
            result,
            ["Peko Pekoyama", "Nagito Komaeda", "Chiaki Nanami"],
        )

    def test_committed_names_lead_interrupted_generation(self):
        result = normalize_character_name_roster(
            ["Replacement", "Third"],
            3,
            committed_names=["Existing"],
        )
        self.assertEqual(result, ["Existing", "Replacement", "Third"])

    def test_deduplicates_case_insensitively_and_fills(self):
        result = normalize_character_name_roster(
            ["Amiya", "amiya", "", {"name": "Gilgamesh"}],
            3,
        )
        self.assertEqual(result, ["Amiya", "Gilgamesh", "Character 1"])

    def test_truncates_overfull_roster_in_order(self):
        result = normalize_character_name_roster(["A", "B", "C"], 2)
        self.assertEqual(result, ["A", "B"])

if __name__ == "__main__":
    unittest.main()
