from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from a2a_dygrade_rl.datasets.build_items import build_items
from a2a_dygrade_rl.datasets.build_papers import build_papers
from a2a_dygrade_rl.datasets.semantic_readiness import audit_semantic_readiness
from a2a_dygrade_rl.datasets.split import assign_prompt_splits
from a2a_dygrade_rl.utils.io import read_jsonl, write_jsonl, write_yaml


def _docx_bytes(essay_set: int, *, with_image: bool = False) -> bytes:
    lines = [
        f"Data Set #{essay_set}",
        "Type of response:", "Source Dependent Response",
        "Grade level:", "10",
        "Subject:", "Science",
        "Final score:", "Final score is score 1. Score 2 is for inter-rater reliability purposes.",
        "Rubric range:", "0-3",
        f"Prompt—Fixture Question {essay_set}",
        f"Use source evidence for fixture set {essay_set}.",
        f"Scoring Rubric for Fixture Question {essay_set}",
        "3 points: complete and correct.",
        "2 points: mostly correct.",
        "1 point: partially correct.",
        "0 points: incorrect.",
    ]
    body = [
        '<w:p><w:r><w:t xml:space="preserve">'
        + line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        + '</w:t></w:r></w:p>'
        for line in lines
    ]
    relationships = ''
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
        if with_image:
            archive.writestr('word/media/image1.jpeg', b'fixture-semantic-v2-image')
    return output.getvalue()


def _write_fixture_raw(root: Path) -> dict[str, Path]:
    asap = root / 'asap_sas'; dress = root / 'dress'
    sas_en = root / 'sas_bench' / 'datasets_en'; sas_ann = root / 'sas_bench' / 'datasets'
    asap.mkdir(parents=True); dress.mkdir(); sas_en.mkdir(parents=True); sas_ann.mkdir(parents=True)
    with ZipFile(asap / 'Data_Set_Descriptions.zip', 'w', ZIP_DEFLATED) as archive:
        for essay_set in (1, 2, 3):
            archive.writestr(
                f'Data Set #{essay_set}--ReadMeFirst.docx',
                _docx_bytes(essay_set, with_image=essay_set == 3),
            )
    asap_lines = ['Id\tEssaySet\tScore1\tScore2\tEssayText']
    source_id = 1
    for essay_set in (1, 2, 3):
        for response in range(2):
            asap_lines.append(f'{source_id}\t{essay_set}\t{response + 1}\t{response + 1}\tASAP answer {essay_set}-{response}.')
            source_id += 1
    (asap / 'train_rel_2.tsv').write_text('\n'.join(asap_lines) + '\n', encoding='utf-8')

    dress_lines = ['id\tsource\tprompt\tessay\tcontent\torganization\tlanguage\ttotal']
    for index in range(3):
        dress_lines.append(f'{index + 1}\tfixture\tEssay prompt {index}.\tEssay response {index}.\t3\t3\t3\t9')
    (dress / 'DREsS_Std.tsv').write_text('\n'.join(dress_lines) + '\n', encoding='utf-8')
    (dress / 'DREsS_New.tsv').write_text(
        'id\tprompt\tessay\tcontent\torganization\tlanguage\ttotal\n'
        '4\tEmpty prompt.\t\t3\t3\t3\t9\n',
        encoding='utf-8',
    )

    english_rows = []
    annotation_rows = []
    for question_index in range(3):
        for response_index in range(2):
            record_id = f'Fixture_{question_index}_{response_index}'
            common = {
                'id': record_id,
                'question': f'SAS question {question_index}.',
                'reference': f'Reference {question_index}.',
                'analysis': f'Analysis {question_index}.',
                'total': 2,
                'manual_label': 1,
                'steps': [{'response': f'Response {question_index}-{response_index}.', 'label': 1, 'errors': []}],
            }
            english_rows.append(common)
            annotation_rows.append(common)
    invalid = {
        'id': 'Fixture_invalid', 'question': 'Bad question.', 'reference': 'Bad reference.', 'analysis': 'Bad analysis.',
        'total': 2, 'manual_label': 1, 'steps': [{'response': '', 'label': 1, 'errors': []}],
    }
    english_rows.append(invalid); annotation_rows.append(invalid)
    def write_jsonl(path: Path, rows: list[dict]) -> None:
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    write_jsonl(sas_en / '0_Physics_ShortAns.translated.jsonl', english_rows)
    write_jsonl(sas_ann / '0_Physics_ShortAns.jsonl', annotation_rows)
    return {'asap': asap, 'dress': dress, 'sas_en': sas_en, 'sas_ann': sas_ann}


def _write_config(path: Path, raw: dict[str, Path]) -> None:
    write_yaml(
        path,
        {
            'run': {'seed': 17, 'rule_version': 'dataset_semantic_group_v2'},
            'datasets': [
                {
                    'name': 'asap_sas', 'raw_path': str(raw['asap']), 'question_type': 'short_answer',
                    'required_essay_sets': ['1', '2', '3'], 'schema_version': 'item_semantic_v2',
                },
                {
                    'name': 'dress', 'raw_path': str(raw['dress']), 'question_type': 'essay',
                    'score_min': 0, 'score_max': 15, 'schema_version': 'item_semantic_v2',
                },
                {
                    'name': 'sas_bench', 'raw_path': str(raw['sas_en']),
                    'annotation_raw_path': str(raw['sas_ann']), 'pattern': '*.translated.jsonl',
                    'schema_version': 'item_semantic_v2',
                },
            ],
            'splits': {'train': 1 / 3, 'dev': 1 / 3, 'test': 1 / 3},
            'paper': {
                'target_items': 5, 'min_items': 5, 'max_items': 5, 'mix_mode': 'strict',
                'rule_version': 'dataset_semantic_paper_v2',
                'strict_quotas': [{'asap_sas': 2, 'sas_bench': 2, 'dress': 1}],
                'budgets': {'max_cost': 1, 'max_elapsed_time': 30, 'max_agent_calls': 5, 'max_a2a_exchanges': 2},
            },
        },
        overwrite=True,
    )


def test_semantic_v2_pipeline_builds_manifests_assets_and_passes_readiness(tmp_path):
    raw = _write_fixture_raw(tmp_path / 'raw')
    config_path = tmp_path / 'dataset_semantic_v2.yaml'
    _write_config(config_path, raw)
    processed = tmp_path / 'processed' / 'semantic_v2'
    output_root = tmp_path / 'outputs' / 'runs'
    build_paths = build_items(
        config_path, processed, 'fixture_semantic_v2', overwrite=True, output_root=output_root
    )
    paper_paths = build_papers(
        config_path, processed, processed, 'fixture_semantic_v2', overwrite=True, output_root=output_root
    )
    assert build_paths['dataset_build_manifest'].exists()
    assert build_paths['quarantine_manifest'].exists()
    assert paper_paths['external_leftovers'].exists()
    manifest = json.loads(build_paths['dataset_build_manifest'].read_text(encoding='utf-8'))
    assert manifest['accepted_item_count'] == 15
    assert manifest['quarantine_count'] == 2
    assert manifest['resource_count'] == 1
    assert all(value == 0 for value in manifest['safety_counters'].values())
    all_items = [item for split in ('train', 'dev', 'test') for item in read_jsonl(processed / f'items_{split}.jsonl')]
    asset = next(item['source_assets'][0] for item in all_items if item['source_assets'])
    assert (processed / asset['relative_path']).exists()
    result = audit_semantic_readiness(
        processed,
        'fixture_semantic_v2',
        config_path=config_path,
        output_root=output_root,
        overwrite=True,
    )
    assert result.passed, result.errors
    assert result.manifest_path is not None and result.manifest_path.exists()


def test_semantic_readiness_fails_closed_when_asap_gold_is_tampered(tmp_path):
    raw = _write_fixture_raw(tmp_path / 'raw')
    config_path = tmp_path / 'dataset_semantic_v2.yaml'
    _write_config(config_path, raw)
    processed = tmp_path / 'processed' / 'semantic_v2'
    output_root = tmp_path / 'outputs' / 'runs'
    build_items(config_path, processed, 'fixture_semantic_v2_bad', overwrite=True, output_root=output_root)
    build_papers(config_path, processed, processed, 'fixture_semantic_v2_bad', overwrite=True, output_root=output_root)
    for split in ('train', 'dev', 'test'):
        path = processed / f'items_{split}.jsonl'
        rows = read_jsonl(path)
        target = next((row for row in rows if row['dataset'] == 'asap_sas'), None)
        if target is not None:
            target['gold_score'] = target['gold_score'] - 1
            write_jsonl(path, rows, overwrite=True)
            break
    result = audit_semantic_readiness(
        processed,
        'fixture_semantic_v2_bad',
        config_path=config_path,
        output_root=output_root,
        overwrite=True,
    )
    assert not result.passed
    assert any('ASAP-SAS' in error or 'Score1' in error for error in result.errors)


def test_cross_dataset_exact_prompt_answer_is_one_component():
    items = []
    for dataset in ('a', 'b'):
        for index in range(4):
            items.append(
                {
                    'item_id': f'{dataset}_{index}', 'dataset': dataset,
                    'prompt': 'shared prompt' if index == 0 else f'{dataset} prompt {index}',
                    'student_answer': 'shared answer' if index == 0 else f'{dataset} answer {index}',
                    'metadata': {'prompt_group': f'{dataset}_group_{index}'},
                }
            )
    split_items = assign_prompt_splits(items, {'train': 0.5, 'dev': 0.25, 'test': 0.25}, 19, 'semantic_v2')
    shared_splits = {
        item['metadata']['split']
        for item in split_items
        if item['prompt'] == 'shared prompt' and item['student_answer'] == 'shared answer'
    }
    assert len(shared_splits) == 1