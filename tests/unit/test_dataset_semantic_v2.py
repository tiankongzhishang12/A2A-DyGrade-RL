from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from a2a_dygrade_rl.datasets.load_asap_sas import load_asap_sas_result
from a2a_dygrade_rl.datasets.load_dress import load_dress_result
from a2a_dygrade_rl.datasets.load_sas_bench import load_sas_bench_result
from a2a_dygrade_rl.utils.model_input import project_model_visible_item


def _docx_bytes(lines: list[str], *, with_image: bool = False) -> bytes:
    body = []
    for line in lines:
        body.append(
            '<w:p><w:r><w:t xml:space="preserve">'
            + line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            + '</w:t></w:r></w:p>'
        )
    relationships = ''
    media = None
    if with_image:
        body.append(
            '<w:p><w:r><w:drawing><wp:inline><a:graphic><a:graphicData>'
            '<pic:pic><pic:blipFill><a:blip r:embed="rIdImage1"/>'
            '</pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline>'
            '</w:drawing></w:r></w:p>'
        )
        relationships = (
            '<Relationship Id="rIdImage1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="media/image1.jpeg"/>'
        )
        media = b'fixture-image-bytes'
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<w:body>' + ''.join(body) + '</w:body></w:document>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + relationships + '</Relationships>'
    )
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', document)
        archive.writestr('word/_rels/document.xml.rels', rels)
        if media is not None:
            archive.writestr('word/media/image1.jpeg', media)
    return output.getvalue()


def _write_asap_fixture(root: Path) -> None:
    root.mkdir(parents=True)
    docx = _docx_bytes(
        [
            'Data Set #1',
            'Type of response:', 'Source Dependent Response',
            'Grade level:', '10',
            'Subject:', 'Science',
            'Final score:', 'Final score is score 1. Score 2 is for inter-rater reliability purposes.',
            'Rubric range:', '0-3',
            'Prompt—Fixture Question',
            'Use the source evidence to answer the question.',
            'Scoring Rubric for Fixture Question',
            '3 points: complete and correct.',
            '2 points: mostly correct.',
            '1 point: partially correct.',
            '0 points: incorrect.',
        ],
        with_image=True,
    )
    with ZipFile(root / 'Data_Set_Descriptions.zip', 'w', ZIP_DEFLATED) as outer:
        outer.writestr('Data Set #1--ReadMeFirst.docx', docx)
    (root / 'train_rel_2.tsv').write_text(
        'Id\tEssaySet\tScore1\tScore2\tEssayText\n'
        '1\t1\t3\t2\tA complete fixture answer.\n',
        encoding='utf-8',
    )


def test_asap_restores_official_prompt_uses_score1_and_preserves_assets(tmp_path):
    root = tmp_path / 'asap'
    _write_asap_fixture(root)
    result = load_asap_sas_result(
        {
            'name': 'asap_sas',
            'raw_path': str(root),
            'question_type': 'short_answer',
            'required_essay_sets': ['1'],
            'schema_version': 'item_semantic_v2',
        },
        resources_root=tmp_path / 'processed' / 'resources',
    )
    assert not result.quarantine
    assert len(result.items) == 1
    item = result.items[0]
    assert item['gold_score'] == 3.0
    assert item['metadata']['score2'] == 2.0
    assert 'Fixture Question' in item['prompt']
    assert 'complete and correct' in item['rubric']
    assert 'See Data_Set_Descriptions.zip' not in item['prompt']
    assert item['source_assets']
    asset = item['source_assets'][0]
    assert asset['sha256']
    assert (tmp_path / 'processed' / asset['relative_path']).exists()
    assert item['metadata']['anchor_mode'] == 'none'


def test_dress_uses_trait_sum_and_quarantines_empty_essay(tmp_path):
    root = tmp_path / 'dress'
    root.mkdir()
    (root / 'DREsS_Std.tsv').write_text(
        'id\tsource\tprompt\tessay\tcontent\torganization\tlanguage\ttotal\n'
        '1\tfixture\tWrite about study.\tA real essay.\t3\t2.5\t4\t9.5\n',
        encoding='utf-8',
    )
    (root / 'DREsS_New.tsv').write_text(
        'id\tprompt\tessay\tcontent\torganization\tlanguage\ttotal\n'
        '2\tWrite about travel.\tAnother essay.\t3\t3\t3\t\n'
        '3\tWrite about travel.\t\t3\t3\t3\t9\n',
        encoding='utf-8',
    )
    (root / 'DREsS_CASE_content.tsv').write_text('ignored', encoding='utf-8')
    result = load_dress_result(
        {
            'name': 'dress',
            'raw_path': str(root),
            'question_type': 'essay',
            'score_min': 0,
            'score_max': 15,
            'schema_version': 'item_semantic_v2',
        }
    )
    assert len(result.items) == 2
    rebuilt = next(item for item in result.items if item['metadata']['source_record_id'] == '2')
    assert rebuilt['gold_score'] == 9.0
    assert rebuilt['metadata']['raw_total_status'] == 'missing'
    assert rebuilt['metadata']['gold_dimensions'] == {'content': 3.0, 'organization': 3.0, 'language': 3.0}
    assert rebuilt['metadata']['anchor_mode'] == 'none'
    assert any(row['reason'] == 'missing_student_essay' for row in result.quarantine)
    assert all('CASE' not in item['metadata']['source_file'] for item in result.items)


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def test_sas_bench_builds_one_whole_response_item_and_hides_step_gold(tmp_path):
    zh = tmp_path / 'zh'
    en = tmp_path / 'en'
    zh.mkdir(); en.mkdir()
    zh_rows = [
        {
            'id': 'q1-r1', 'question': '问题', 'analysis': '解析', 'reference': '参考',
            'total': 3, 'manual_label': 2,
            'steps': [
                {'response': '第一步', 'label': 1, 'errors': []},
                {'response': '第二步', 'label': 1, 'errors': []},
            ],
        },
        {
            'id': 'q2-r1', 'question': '问题2', 'analysis': '解析2', 'reference': '参考2',
            'total': 2, 'manual_label': 1,
            'steps': [{'response': '', 'label': 1, 'errors': []}],
        },
    ]
    en_rows = [
        {
            'id': 'q1-r1', 'question': 'Question', 'analysis': 'Analysis', 'reference': 'Reference',
            'total': 3, 'manual_label': 2,
            'steps': [
                {'response': 'First step', 'label': 1, 'errors': []},
                {'response': 'Second step', 'label': 1, 'errors': []},
            ],
        },
        {
            'id': 'q2-r1', 'question': 'Question 2', 'analysis': 'Analysis 2', 'reference': 'Reference 2',
            'total': 2, 'manual_label': 1,
            'steps': [{'response': '', 'label': 1, 'errors': []}],
        },
    ]
    _write_jsonl(zh / '0_Physics_ShortAns.jsonl', zh_rows)
    _write_jsonl(en / '0_Physics_ShortAns.translated.jsonl', en_rows)
    result = load_sas_bench_result(
        {
            'name': 'sas_bench',
            'raw_path': str(en),
            'annotation_raw_path': str(zh),
            'pattern': '*.translated.jsonl',
            'schema_version': 'item_semantic_v2',
        }
    )
    assert len(result.items) == 1
    item = result.items[0]
    assert item['gold_score'] == 2.0
    assert item['score_max'] == 3.0
    assert '[Step 1]' in item['student_answer'] and '[Step 2]' in item['student_answer']
    assert item['metadata']['scoring_unit'] == 'whole_response'
    assert item['metadata']['hidden_step_labels'] == [1.0, 1.0]
    visible = project_model_visible_item(item)
    serialized = json.dumps(visible, ensure_ascii=False)
    assert 'hidden_step_labels' not in serialized
    assert 'manual_label' not in serialized
    assert any(row['reason'] == 'empty_step_with_nonzero_label' for row in result.quarantine)


def test_agent_context_projection_removes_all_hidden_gold_fields():
    from a2a_dygrade_rl.agents.base_agent import strip_gold
    from a2a_dygrade_rl.utils.model_input import find_banned_keys

    context = {
        'gold_score': 2,
        'nested': {
            'manual_label': 2,
            'hidden_step_labels': [1, 1],
            'gold_dimensions': {'content': 1},
        },
        'safe': 'visible context',
    }
    projected = strip_gold(context)
    assert projected['safe'] == 'visible context'
    assert find_banned_keys(projected) == []