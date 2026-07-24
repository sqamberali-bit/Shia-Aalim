import json

from shia_aalim.ingestion.adapters.quran import build_quran_documents
from shia_aalim.models import Document


def _edition(path, verses):
    path.write_text(json.dumps({"quran": verses}, ensure_ascii=False), encoding="utf-8")


def test_quran_adapter_attaches_arabic_english_and_urdu(tmp_path):
    ar = tmp_path / "ar.json"
    en = tmp_path / "en.json"
    ur = tmp_path / "ur.json"
    _edition(ar, [{"chapter": 5, "verse": 55, "text": "إِنَّمَا وَلِيُّكُمُ اللَّهُ"}])
    _edition(en, [{"chapter": 5, "verse": 55, "text": "Your guardian is only Allah"}])
    _edition(ur, [{"chapter": 5, "verse": 55, "text": "تمہارا ولی صرف اللہ ہے"}])

    docs = build_quran_documents(
        ar, en, translation_name="EN", urdu_path=ur, urdu_name="Jawadi",
    )
    assert len(docs) == 1
    c = docs[0].citation
    assert c.arabic_text.startswith("إِنَّمَا")
    assert c.translation == "Your guardian is only Allah"
    assert c.translation_ur == "تمہارا ولی صرف اللہ ہے"
    assert c.translation_ur_source == "Jawadi"


def test_quran_adapter_without_urdu_leaves_it_none(tmp_path):
    ar = tmp_path / "ar.json"
    en = tmp_path / "en.json"
    _edition(ar, [{"chapter": 1, "verse": 1, "text": "بِسْمِ اللَّهِ"}])
    _edition(en, [{"chapter": 1, "verse": 1, "text": "In the name of Allah"}])
    docs = build_quran_documents(ar, en, translation_name="EN")
    assert docs[0].citation.translation_ur is None
    assert docs[0].citation.translation_ur_source is None


def test_urdu_survives_json_round_trip(tmp_path):
    ar = tmp_path / "ar.json"; en = tmp_path / "en.json"; ur = tmp_path / "ur.json"
    _edition(ar, [{"chapter": 112, "verse": 1, "text": "قُلْ هُوَ اللَّهُ أَحَدٌ"}])
    _edition(en, [{"chapter": 112, "verse": 1, "text": "Say, He is Allah, the One"}])
    _edition(ur, [{"chapter": 112, "verse": 1, "text": "کہہ دیجئے وہ اللہ ایک ہے"}])
    doc = build_quran_documents(ar, en, translation_name="EN", urdu_path=ur, urdu_name="Jawadi")[0]
    rt = Document.from_dict(json.loads(doc.to_json_line()))
    assert rt.citation.translation_ur == "کہہ دیجئے وہ اللہ ایک ہے"
    assert rt.citation.translation_ur_source == "Jawadi"
