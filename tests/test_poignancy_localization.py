import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
    / "three_estates_sim"
    / "backend_server"
)
sys.path.insert(0, str(BACKEND_ROOT))

from utils import (
    deterministic_chat_poignancy_score,
    event_role_keywords_from_text,
    heuristic_poignancy_score,
    role_keywords_from_text,
)


def strategic_persona(name, names):
    room = SimpleNamespace(
        conversation_mode="strategic",
        personas={other_name: None for other_name in names},
    )
    return SimpleNamespace(scratch=SimpleNamespace(name=name), room=room)


class LocalizedPoignancyTests(unittest.TestCase):
    def test_chinese_name_and_role_scores_match_english_scale(self):
        persona = strategic_persona("本条二亚", ["本条二亚", "夜刀神十香"])
        self.assertEqual(
            deterministic_chat_poignancy_score(
                persona,
                "本条二亚，你是旅店老板，属于平民。",
            ),
            9,
        )
        self.assertEqual(
            deterministic_chat_poignancy_score(
                persona,
                "夜刀神十香是国王，属于贵族。",
            ),
            8,
        )
        self.assertEqual(
            deterministic_chat_poignancy_score(persona, "我觉得那个国王在撒谎。"),
            5,
        )

    def test_japanese_identity_spaces_are_optional_in_natural_prose(self):
        persona = strategic_persona(
            "本条 二亜",
            ["本条 二亜", "夜刀神 十香"],
        )
        self.assertEqual(
            deterministic_chat_poignancy_score(
                persona,
                "夜刀神十香は王で、貴族だ。",
            ),
            8,
        )
        self.assertEqual(
            deterministic_chat_poignancy_score(
                persona,
                "本条二亜は宿屋の主人で、平民だ。",
            ),
            9,
        )

    def test_single_character_japanese_role_avoids_compound_false_positives(self):
        persona = strategic_persona("本条 二亜", ["本条 二亜", "夜刀神 十香"])
        self.assertEqual(
            deterministic_chat_poignancy_score(persona, "あの魔王は本当に騒がしい。"),
            2,
        )
        self.assertEqual(
            deterministic_chat_poignancy_score(persona, "私は王だ。"),
            5,
        )

    def test_canonical_dialogue_keywords_are_authoritative(self):
        persona = strategic_persona("本条二亚", ["本条二亚", "夜刀神十香"])
        self.assertEqual(
            heuristic_poignancy_score(
                persona,
                "chat",
                "本条二亚，这个身份很可疑。",
                keywords={"King", "Nobility"},
            ),
            9,
        )

    def test_localized_plain_movement_remains_low_importance(self):
        persona = strategic_persona("本条二亚", ["本条二亚", "夜刀神十香"])
        self.assertEqual(
            heuristic_poignancy_score(
                persona,
                "event",
                "夜刀神十香 离开并前往村庄。",
                subject="夜刀神十香",
            ),
            1,
        )
        self.assertEqual(
            heuristic_poignancy_score(
                persona,
                "event",
                "夜刀神 十香は村へ向かう。",
                subject="夜刀神 十香",
            ),
            1,
        )

    def test_localized_role_event_keywords_preserve_proof_score(self):
        persona = strategic_persona("本条二亚", ["本条二亚", "夜刀神十香"])
        self.assertEqual(
            heuristic_poignancy_score(
                persona,
                "event",
                "夜刀神十香 亮出自己的国王牌。",
                subject="夜刀神十香",
            ),
            7,
        )

    def test_keyword_extraction_understands_every_installed_locale(self):
        self.assertTrue(
            {"Innkeeper", "Commoners"}.issubset(
                role_keywords_from_text("她自称旅店老板，属于平民。")
            )
        )
        self.assertTrue(
            {"Innkeeper", "Commoners"}.issubset(
                role_keywords_from_text("彼女は宿屋の主人で、平民だ。")
            )
        )
        self.assertTrue(
            {"King", "Nobility"}.issubset(
                event_role_keywords_from_text("彼女は王カードを公開し、貴族だと証明する。")
            )
        )


if __name__ == "__main__":
    unittest.main()
