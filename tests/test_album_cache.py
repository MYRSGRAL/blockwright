"""Сохранённая ручная правка принадлежит конкретной версии генерации."""

import json
import re
import shutil
import subprocess
import unittest

from blockwright.album import JS_APP, JS_CORE, render_html


class AlbumRevision(unittest.TestCase):
    def revision(self, text: str, folder: str = "пример", theme: str = "light") -> str:
        entries = [{"anchor": "1__main", "model": {"text": text}}]
        page = render_html(entries, folder=folder, theme=theme)
        payload = json.loads(re.search(r"const DATA=(.*);</script>", page).group(1))
        return payload["revision"]

    def test_revision_tracks_model_and_album_but_not_interface_theme(self) -> None:
        original = self.revision("Ввод x")
        self.assertEqual(original, self.revision("Ввод x"))
        self.assertEqual(original, self.revision("Ввод x", theme="dark"))
        self.assertNotEqual(original, self.revision("Ввод a[n]"))
        self.assertNotEqual(original, self.revision("Ввод x", folder="другая папка"))


@unittest.skipUnless(shutil.which("node"), "Для проверки редактора нужен Node.js")
class SavedCharts(unittest.TestCase):
    def load(self, cache: dict[str, str]) -> dict:
        script = (
            "const DATA={revision:'current',items:[],lang:'ru',theme:'light'};\n"
            + "const cache=new Map(Object.entries("
            + json.dumps(cache)
            + "));\n"
            + "const localStorage={getItem:k=>cache.get(k)||null,setItem:(k,v)=>cache.set(k,v)};\n"
            + JS_CORE
            + JS_APP.split("function saveStore")[0]
            + "\nloadStore();process.stdout.write(JSON.stringify({docs,cache:Object.fromEntries(cache)}));"
        )
        result = subprocess.run(
            ["node"], input=script, encoding="utf-8", capture_output=True, check=True
        )
        return json.loads(result.stdout)

    def test_legacy_and_other_generation_are_preserved_without_overriding_fresh_model(
        self,
    ) -> None:
        old = json.dumps(
            {
                "docs": {"1__main": {"text": "Старая длинная схема"}},
                "dirty": ["1__main"],
            }
        )
        cache = {"blockwright.cpp.v1": old, "blockwright.cpp.v2.previous": old}
        result = self.load(cache)
        self.assertEqual(result["docs"], {})
        self.assertEqual(result["cache"], cache)

    def test_edits_of_current_generation_are_restored(self) -> None:
        docs = {"1__main": {"text": "Ручная правка актуальной схемы"}}
        result = self.load({"blockwright.cpp.v2.current": json.dumps({"docs": docs})})
        self.assertEqual(result["docs"], docs)


if __name__ == "__main__":
    unittest.main()
