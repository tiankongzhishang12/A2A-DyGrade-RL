from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.datasets.download import check_expected_files, download_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="按 manifest 下载或检查 raw datasets")
    parser.add_argument("--manifest", default="configs/dataset_sources.yaml")
    parser.add_argument("--check-only", action="store_true", help="只检查本地授权文件是否存在")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已下载文件")
    args = parser.parse_args()
    results = check_expected_files(args.manifest) if args.check_only else download_sources(args.manifest, args.overwrite)
    for result in results:
        print(f"{result['name']}\t{result['status']}\t{result['target_dir']}\t{result['message']}")


if __name__ == "__main__":
    main()
