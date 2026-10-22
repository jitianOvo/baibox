"""仅清理本项目中可再生成的缓存；默认预览，--apply 执行。"""
import argparse
import json
import os
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
FIXED = ("data/cache", "work/media-hub-tests", "libs/phone_trace_recorder/temp")


def checked(path):
    path = Path(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or resolved == ROOT.resolve():
        raise ValueError(f"清理路径超出项目范围：{path}")
    relative = path.absolute().relative_to(ROOT.absolute())
    cursor = ROOT
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ValueError(f"跳过链接目录：{cursor}")
    return path


def targets():
    result = []
    for directory, dirs, _ in os.walk(ROOT, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if name in {".git", ".archive", ".venv", "venv", "node_modules"} or path.is_symlink() or (
                    hasattr(path, "is_junction") and path.is_junction()):
                dirs.remove(name)
            elif name in CACHE_NAMES:
                result.append(checked(path))
                dirs.remove(name)
    result.extend(checked(ROOT / name) for name in FIXED if (ROOT / name).exists())
    return sorted(set(result), key=str)


def remove_readonly(function, path, exception):
    if isinstance(exception, PermissionError):
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        function(path)
    else:
        raise exception


def clean(apply=False):
    report = dict(root=str(ROOT), apply=apply, files=0, bytes=0, removed=[], failed=[])
    for path in targets():
        try:
            checked(path)
            files = [p for p in path.rglob("*") if p.is_file() and not p.is_symlink()]
            size = sum(p.stat().st_size for p in files)
            if apply:
                shutil.rmtree(path, onerror=lambda fn, p, info: remove_readonly(fn, p, info[1]))
            report["files"] += len(files)
            report["bytes"] += size
            report["removed"].append(path.relative_to(ROOT).as_posix())
        except (OSError, ValueError) as exc:
            report["failed"].append(dict(path=str(path), error=str(exc)))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际清理；否则仅预览")
    args = parser.parse_args()
    print(json.dumps(clean(args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
