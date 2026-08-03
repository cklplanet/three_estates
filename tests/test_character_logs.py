import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
    / "three_estates_sim"
    / "backend_server"
)
sys.path.insert(0, str(BACKEND_ROOT))

import utils


class CharacterLogTests(unittest.TestCase):
    def test_character_logs_use_registered_unicode_names_only(self):
        names = {
            "C.C.",
            "鲁鲁修·兰佩路基",
            "“Saber”阿尔托莉雅·潘德拉贡",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            utils.set_advanced_log_dirs(temp_dir, character_names=names)
            utils.append_character_specific_log(
                {
                    "鲁鲁修·兰佩路基",
                    "King",
                    "Commoners",
                    "Forest",
                    "everyone",
                },
                "event line",
            )
            character_dir = Path(temp_dir) / "characters"
            files = {path.name for path in character_dir.glob("*.log")}
            self.assertEqual(files, {"鲁鲁修_兰佩路基.log"})
            self.assertEqual(
                (character_dir / "鲁鲁修_兰佩路基.log").read_text(
                    encoding="utf-8"
                ),
                "event line\n",
            )

            utils.append_all_character_specific_logs(
                "overheard line",
                exclude_characters={"鲁鲁修·兰佩路基"},
            )
            files = {path.name for path in character_dir.glob("*.log")}
            self.assertEqual(
                files,
                {
                    "C.C.log",
                    "Saber_阿尔托莉雅_潘德拉贡.log",
                    "鲁鲁修_兰佩路基.log",
                },
            )
            self.assertNotIn("unknown.log", files)
            self.assertNotIn("King.log", files)

    def test_remote_scream_log_omits_unseen_expression_and_action(self):
        names = {"Speaker", "Witness", "Remote"}
        with tempfile.TemporaryDirectory() as temp_dir:
            detailed = Path(temp_dir) / "dialogue.log"
            clean = Path(temp_dir) / "clean.log"
            with patch("localization.ACTIVE_LOCALE", "en-US"):
                utils.set_dialogue_log_path(
                    detailed,
                    log_dir=temp_dir,
                    character_names=names,
                )
                utils.set_clean_dialogue_log_path(clean)
                utils.write_dialogue_log(
                    "Forest",
                    (
                        "Speaker",
                        "Witness",
                        "practically screaming",
                        "furious",
                        "slams a card down",
                        "You heard me!",
                        "0:00:10",
                        {"Speaker", "Witness"},
                        set(),
                    ),
                )
            remote_log = (
                Path(temp_dir) / "characters" / "Remote.log"
            ).read_text(encoding="utf-8")
            self.assertIn("[practically screaming]: You heard me!", remote_log)
            self.assertNotIn("furious", remote_log)
            self.assertNotIn("slams a card down", remote_log)


if __name__ == "__main__":
    unittest.main()
