"""
Convert shortcut_full_dataset.csv to bug_corpus.json format
"""
import csv
import json
from pathlib import Path

def parse_bug_description(desc_text: str) -> dict:
    """
    Parse bug description to extract Vietnamese and English parts.
    Format: "Vietnamese text // English text" or just one language
    """
    if not desc_text or desc_text.strip() == "":
        return {"desc_vi": "", "desc_en": "", "desc_full": ""}

    desc_text = desc_text.strip()

    # Check if it contains "//" separator
    if "//" in desc_text:
        parts = desc_text.split("//", 1)
        vi_part = parts[0].strip()
        en_part = parts[1].strip() if len(parts) > 1 else ""

        # Determine which is Vietnamese and which is English
        # If first part contains Vietnamese characters, it's Vietnamese
        if any(ord(c) > 127 for c in vi_part):
            desc_vi = vi_part
            desc_en = en_part
        else:
            desc_vi = en_part if any(ord(c) > 127 for c in en_part) else ""
            desc_en = vi_part
    else:
        # No separator, check language
        if any(ord(c) > 127 for c in desc_text):
            desc_vi = desc_text
            desc_en = ""
        else:
            desc_vi = ""
            desc_en = desc_text

    desc_full = f"{desc_vi}//\n\n{desc_en}".strip() if desc_vi and desc_en else (desc_vi or desc_en)

    return {
        "desc_vi": desc_vi,
        "desc_en": desc_en,
        "desc_full": desc_full
    }


def convert_csv_to_corpus(csv_path: str, output_path: str):
    """Convert CSV to bug_corpus.json format"""
    bugs = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bug_id = int(row['Bug Id'])
            root_url = row['Root Url'].strip()
            short_desc = row['Short Description'].strip()

            # Parse description
            parsed = parse_bug_description(short_desc)

            bug = {
                "bug_id": bug_id,
                "root_url": root_url,
                "desc_vi": parsed["desc_vi"],
                "desc_en": parsed["desc_en"],
                "desc_full": parsed["desc_full"]
            }
            bugs.append(bug)

    # Sort by bug_id
    bugs.sort(key=lambda x: x['bug_id'])

    # Count statistics
    total = len(bugs)
    bilingual = sum(1 for b in bugs if b['desc_vi'] and b['desc_en'])
    en_only = sum(1 for b in bugs if b['desc_en'] and not b['desc_vi'])
    vi_only = sum(1 for b in bugs if b['desc_vi'] and not b['desc_en'])

    # Count unique root URLs
    unique_urls = set(b['root_url'] for b in bugs)

    corpus = {
        "metadata": {
            "total_bugs": total,
            "bilingual_count": bilingual,
            "english_only_count": en_only,
            "vietnamese_only_count": vi_only,
            "unique_root_urls": len(unique_urls),
            "root_urls": sorted(list(unique_urls)),
            "source": "shortcut_full_dataset.csv"
        },
        "bugs": bugs
    }

    # Write to JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    print(f"[OK] Converted {total} bugs to {output_path}")
    print(f"  - Bilingual: {bilingual}")
    print(f"  - English only: {en_only}")
    print(f"  - Vietnamese only: {vi_only}")
    print(f"  - Unique root URLs: {len(unique_urls)}")
    for url in sorted(unique_urls):
        count = sum(1 for b in bugs if b['root_url'] == url)
        print(f"    - {url}: {count} bugs")


if __name__ == "__main__":
    csv_path = Path(__file__).parent / "raw" / "shortcut_full_dataset.csv"
    output_path = Path(__file__).parent / "bug_corpus_full.json"

    convert_csv_to_corpus(str(csv_path), str(output_path))
