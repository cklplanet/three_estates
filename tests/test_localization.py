import datetime
import ast
import json
import sys
import unittest
from pathlib import Path
from string import Formatter
from unittest.mock import patch


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
    / "three_estates_sim"
    / "backend_server"
)
sys.path.insert(0, str(BACKEND_ROOT))

from localization import (
    display_name,
    localized_prompt_data,
    localized_prompt_path,
    normalize_locale,
    protocol_display_name,
    tr,
)
from global_methods import timedelta_to_natural
from utils import (
    build_prefix,
    compact_summary_text,
    event_role_keywords_from_text,
    localize_transcript_natural_text,
)


class LocalizationTests(unittest.TestCase):
    def test_locale_aliases_are_normalized(self):
        self.assertEqual(normalize_locale("zh_Hans"), "zh-CN")
        self.assertEqual(normalize_locale("en"), "en-US")
        self.assertEqual(normalize_locale("ja"), "ja-JP")
        self.assertEqual(normalize_locale("jp"), "ja-JP")

    def test_missing_key_falls_back_to_caller_default(self):
        self.assertEqual(
            tr("missing.example", default="fallback", locale="zh-CN"),
            "fallback",
        )

    def test_epilogue_count_excludes_blank_separator_lines(self):
        chinese = tr("prompt.epilogue_content_count", locale="zh-CN", count=60)
        japanese = tr("prompt.epilogue_content_count", locale="ja-JP", count=60)
        self.assertIn("60 条实际场景内容", chinese)
        self.assertIn("空白分隔行", chinese)
        self.assertIn("不计入", chinese)
        self.assertIn("約60件", japanese)
        self.assertIn("空行", japanese)

    def test_spinster_guess_uses_its_dedicated_model_route(self):
        source = (
            BACKEND_ROOT
            / "persona"
            / "prompt_template"
            / "run_gpt_prompt.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "run_gpt_prompt_spinster_endgame_guess"
        )
        referenced_names = {
            node.id for node in ast.walk(function) if isinstance(node, ast.Name)
        }
        self.assertIn("SPINSTER_GUESS_LLM_MODEL", referenced_names)

    def test_chinese_display_names_keep_canonical_ids_separate(self):
        self.assertEqual(display_name("table", "Castle", locale="zh-CN"), "城堡")
        self.assertEqual(display_name("role", "Bishop", locale="zh-CN"), "主教")
        self.assertEqual(display_name("role", "Spinster", locale="zh-CN"), "纺纱女")
        self.assertEqual(
            display_name("role_card", "Innkeeper", locale="zh-CN"),
            "旅店老板牌",
        )
        self.assertEqual(display_name("volume", "whisper", locale="zh-CN"), "低声")
        self.assertEqual(display_name("volume", "calm", locale="zh-CN"), "平静")
        self.assertEqual(display_name("volume", "loud", locale="zh-CN"), "大声")
        self.assertEqual(
            display_name("volume", "practically screaming", locale="zh-CN"),
            "近乎喊叫",
        )
        self.assertEqual(
            display_name("dialogue_target", "everyone", locale="zh-CN"),
            "全桌",
        )
        self.assertEqual(
            display_name("event_actor", "system", locale="zh-CN"),
            "系统",
        )
        self.assertEqual(display_name("family", "Nobility", locale="zh-CN"), "贵族")
        self.assertEqual(display_name("family", "Commoners", locale="zh-CN"), "平民")
        self.assertEqual(display_name("family", "Clergy", locale="zh-CN"), "神职者")

    def test_japanese_display_names_keep_canonical_ids_separate(self):
        self.assertEqual(display_name("table", "Forest", locale="ja-JP"), "森")
        self.assertEqual(display_name("role", "Spinster", locale="ja-JP"), "糸紡ぎ女")
        self.assertEqual(
            display_name("role_card", "Innkeeper", locale="ja-JP"),
            "宿屋の主人カード",
        )
        self.assertEqual(
            display_name("volume", "practically screaming", locale="ja-JP"),
            "ほとんど叫び声",
        )
        self.assertEqual(
            display_name("dialogue_target", "everyone", locale="ja-JP"),
            "テーブル全員",
        )
        self.assertEqual(display_name("family", "Commoners", locale="ja-JP"), "平民")

    def test_japanese_prose_may_omit_roster_name_separator(self):
        instruction = tr("prompt.language_instruction", locale="ja-JP")
        self.assertIn("識別値は「夜神 月」", instruction)
        self.assertIn("本文では「夜神月」", instruction)

    def test_non_english_rulebooks_use_bilingual_role_and_family_glossary(self):
        with patch("localization.ACTIVE_LOCALE", "zh-CN"):
            self.assertEqual(
                protocol_display_name("role", "Spinster"),
                "纺纱女（Spinster）",
            )
            chinese_prefix = build_prefix("10")
        self.assertIn("纺纱女（Spinster）", chinese_prefix)
        self.assertIn("平民（Commoners）", chinese_prefix)
        self.assertIn("LOCALIZED ROLE/FAMILY GLOSSARY", chinese_prefix)

        with patch("localization.ACTIVE_LOCALE", "ja-JP"):
            japanese_prefix = build_prefix("10")
        self.assertIn("糸紡ぎ女（Spinster）", japanese_prefix)
        self.assertIn("聖職者（Clergy）", japanese_prefix)

        with patch("localization.ACTIVE_LOCALE", "en-US"):
            english_prefix = build_prefix("10")
        self.assertNotIn("LOCALIZED ROLE/FAMILY GLOSSARY", english_prefix)

    def test_bishop_events_localize_without_changing_protocol_values(self):
        rendered = tr(
            "event.bishop.attempt",
            locale="zh-CN",
            bishop="鲁鲁修",
            role=display_name("role", "Bishop", locale="zh-CN"),
            target="吉尔伽美什",
            family=display_name("family", "Nobility", locale="zh-CN"),
        )
        self.assertEqual(
            rendered,
            "鲁鲁修 亮出自己的主教牌，猜测 吉尔伽美什 属于贵族并尝试发动主教能力。",
        )

    def test_king_ability_target_family_can_be_rendered_in_chinese(self):
        rendered = tr(
            "event.ability.attempt",
            locale="zh-CN",
            character="阿尔托莉雅",
            role=display_name("role", "King", locale="zh-CN"),
            target=display_name("family", "Commoners", locale="zh-CN"),
        )
        self.assertEqual(
            rendered,
            "阿尔托莉雅 亮出自己的国王牌，并尝试对平民发动国王能力。",
        )

    def test_every_referenced_system_event_is_translated_in_each_locale(self):
        referenced_keys = set()
        for source_path in BACKEND_ROOT.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "tr"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    continue
                key = str(node.args[0].value)
                if key.startswith("event.") and "{" not in key:
                    referenced_keys.add(key)
        english = json.loads(
            (BACKEND_ROOT / "locales" / "en-US" / "strings.json").read_text(
                encoding="utf-8"
            )
        )
        chinese = json.loads(
            (BACKEND_ROOT / "locales" / "zh-CN" / "strings.json").read_text(
                encoding="utf-8"
            )
        )
        japanese = json.loads(
            (BACKEND_ROOT / "locales" / "ja-JP" / "strings.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(referenced_keys)
        self.assertFalse(referenced_keys - set(english))
        self.assertFalse(referenced_keys - set(chinese))
        self.assertFalse(referenced_keys - set(japanese))
        for key in referenced_keys:
            self.assertNotEqual(english[key], chinese[key], key)
            self.assertNotEqual(english[key], japanese[key], key)

    def test_locale_catalogs_have_identical_key_sets(self):
        catalogs = {}
        for locale in ("en-US", "zh-CN", "ja-JP"):
            catalogs[locale] = json.loads(
                (BACKEND_ROOT / "locales" / locale / "strings.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(set(catalogs["en-US"]), set(catalogs["zh-CN"]))
        self.assertEqual(set(catalogs["en-US"]), set(catalogs["ja-JP"]))
        for key, english_value in catalogs["en-US"].items():
            english_fields = {
                field
                for _literal, field, _spec, _conversion in Formatter().parse(
                    english_value
                )
                if field
            }
            for locale in ("zh-CN", "ja-JP"):
                localized_fields = {
                    field
                    for _literal, field, _spec, _conversion in Formatter().parse(
                        catalogs[locale][key]
                    )
                    if field
                }
                self.assertEqual(localized_fields, english_fields, (locale, key))

    def test_localized_event_text_retains_canonical_retrieval_keywords(self):
        with patch("localization.ACTIVE_LOCALE", "zh-CN"):
            keywords = event_role_keywords_from_text(
                "鲁鲁修亮出主教牌，猜测吉尔伽美什属于贵族。"
            )
        self.assertIn("Bishop", keywords)
        self.assertIn("Clergy", keywords)
        self.assertIn("Nobility", keywords)

    def test_chinese_transcript_localizes_card_names_leaked_into_prose(self):
        with patch("localization.ACTIVE_LOCALE", "zh-CN"):
            self.assertEqual(
                localize_transcript_natural_text("啪地把 Priest 卡拍在桌上"),
                "啪地把神父牌拍在桌上",
            )
            self.assertEqual(
                localize_transcript_natural_text("猛地高举Thief卡往后缩"),
                "猛地高举盗贼牌往后缩",
            )
            self.assertEqual(
                localize_transcript_natural_text("King 仍然只是称号"),
                "King 仍然只是称号",
            )

    def test_english_transcript_keeps_canonical_card_names(self):
        with patch("localization.ACTIVE_LOCALE", "en-US"):
            self.assertEqual(
                localize_transcript_natural_text("reveals the Priest card"),
                "reveals the Priest card",
            )

    def test_japanese_transcript_localizes_card_names_leaked_into_prose(self):
        with patch("localization.ACTIVE_LOCALE", "ja-JP"):
            self.assertEqual(
                localize_transcript_natural_text("Priest カードをテーブルに置く"),
                "司祭カードをテーブルに置く",
            )

    def test_reasoning_limits_come_from_the_active_locale(self):
        english = localized_prompt_data({}, locale="en-US")
        chinese = localized_prompt_data({}, locale="zh-CN")
        japanese = localized_prompt_data({}, locale="ja-JP")
        self.assertIn("50 English words", english["short_reasoning_limit"])
        self.assertIn("150 个中文字符", chinese["short_reasoning_limit"])
        self.assertIn("250 English words", english["movement_reasoning_limit"])
        self.assertIn("750 个中文字符", chinese["movement_reasoning_limit"])
        self.assertIn("100 English words", english["innate_profile_limit"])
        self.assertIn("300 个中文字符", chinese["innate_profile_limit"])
        self.assertIn("120 English words", english["relationship_limit"])
        self.assertIn("360 个中文字符", chinese["relationship_limit"])
        self.assertIn("180文字", japanese["short_reasoning_limit"])
        self.assertIn("900文字", japanese["movement_reasoning_limit"])
        self.assertIn("360文字", japanese["innate_profile_limit"])
        self.assertIn("432文字", japanese["relationship_limit"])

    def test_compact_summary_normalizes_without_truncating(self):
        long_summary = "move " * 100
        self.assertEqual(
            compact_summary_text(long_summary),
            long_summary.strip(),
        )

    def test_chinese_prompt_override_is_selected(self):
        selected = localized_prompt_path(
            "persona/prompt_template/templates/generate_next_convo_line_normal.txt",
            locale="zh-CN",
        )
        self.assertEqual(selected.parent.parent.name, "zh-CN")

    def test_japanese_prompt_override_is_selected(self):
        selected = localized_prompt_path(
            "persona/prompt_template/templates/generate_next_convo_line_normal.txt",
            locale="ja-JP",
        )
        self.assertEqual(selected.parent.parent.name, "ja-JP")

    def test_chinese_terminal_choices_show_english_aliases(self):
        self.assertIn("（casual）", tr("terminal.choose_conversation_mode", locale="zh-CN"))
        self.assertIn("（yes）", tr("terminal.choose_manual_seating", locale="zh-CN"))
        self.assertIn("（keep）", tr("terminal.choose_context_mode", locale="zh-CN"))
        self.assertIn("（same roles）", tr("terminal.session_found", locale="zh-CN"))
        self.assertIn("（immersion）", tr("terminal.choose_generation_mode", locale="zh-CN"))
        self.assertIn("（custom）", tr("terminal.choose_clothing", locale="zh-CN"))

    def test_japanese_terminal_choices_show_english_aliases(self):
        self.assertIn("（casual）", tr("terminal.choose_conversation_mode", locale="ja-JP"))
        self.assertIn("（yes）", tr("terminal.choose_manual_seating", locale="ja-JP"))
        self.assertIn("（keep）", tr("terminal.choose_context_mode", locale="ja-JP"))
        self.assertIn("（same roles）", tr("terminal.session_found", locale="ja-JP"))
        self.assertIn("（immersion）", tr("terminal.choose_generation_mode", locale="ja-JP"))
        self.assertIn("（custom）", tr("terminal.choose_clothing", locale="ja-JP"))

    def test_active_locale_formats_durations(self):
        rendered = timedelta_to_natural(datetime.timedelta(minutes=2, seconds=3))
        self.assertTrue(rendered)


if __name__ == "__main__":
    unittest.main()
