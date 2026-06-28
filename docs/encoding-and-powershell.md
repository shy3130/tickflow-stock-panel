# Encoding Guardrails For Windows PowerShell

## Root Cause

The source files in this repository are UTF-8. Files such as:

- `backend/app/api/kline.py`
- `backend/app/api/indices.py`
- `backend/app/jobs/daily_pipeline.py`

decode correctly as UTF-8 and contain no replacement characters when read with Python or with explicit UTF-8.

The mojibake came from the Windows PowerShell 5.1 shell environment, not from the files themselves:

- `[Console]::InputEncoding` was GB2312 / code page 936.
- `$OutputEncoding` was US-ASCII.
- `Get-Content` without `-Encoding UTF8` is not safe in this environment.
- `Set-Content` without an explicit UTF-8 encoding can write the already-misdecoded text back to disk.

That chain can turn a valid UTF-8 file into a broken file:

1. A UTF-8 file is read through PowerShell's legacy/default encoding path.
2. Chinese text is displayed as mojibake.
3. If that mojibake string is written back with `Set-Content`, the file is corrupted.
4. Python may then fail with syntax errors around damaged comments, docstrings, or string literals.

This is why a file can look broken in terminal output while still being valid on disk.

## Rules

Do not use these commands on files that may contain non-ASCII text:

```powershell
Get-Content path\file.py
Set-Content path\file.py -Value $text
git show HEAD:path/file.py | Set-Content path\file.py
```

Use one of these safe approaches instead.

For reading:

```powershell
Get-Content path\file.py -Encoding UTF8
```

For writing with PowerShell 5.1, prefer .NET and UTF-8 without BOM:

```powershell
$path = Resolve-Path "path\file.py"
$text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($path, $text, [System.Text.UTF8Encoding]::new($false))
```

For manual code edits, prefer `apply_patch`. It preserves file bytes better than shell read/modify/write loops.

For bulk or scripted edits, use Python with explicit UTF-8:

```powershell
@'
from pathlib import Path

p = Path("path/file.py")
text = p.read_text(encoding="utf-8")
text = text.replace("old", "new")
p.write_text(text, encoding="utf-8", newline="")
'@ | python -
```

## Diagnostics

Check whether a file is really UTF-8:

```powershell
@'
from pathlib import Path

for p in [Path("backend/app/api/kline.py")]:
    b = p.read_bytes()
    print(p)
    print("first bytes:", b[:8].hex(" "))
    s = b.decode("utf-8")
    print("replacement chars:", s.count(chr(0xfffd)))
    print("preview:", repr(s[:80]))
'@ | python -
```

Expected result:

- UTF-8 decode succeeds.
- `replacement chars` is `0`.

Check Git line ending state:

```powershell
git ls-files --eol backend/app/api/kline.py backend/app/api/indices.py backend/app/jobs/daily_pipeline.py
```

Line-ending warnings are separate from encoding. They are not the mojibake cause.

## Recovery

If a file starts showing syntax errors after a PowerShell write:

1. Restore the file from Git.
2. Rewrite it as UTF-8 without BOM.
3. Reapply only the intended patch.
4. Compile/test immediately.

Safe restore pattern:

```powershell
git checkout -- path/to/file.py
$path = Resolve-Path "path\to\file.py"
$text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($path, $text, [System.Text.UTF8Encoding]::new($false))
python -m py_compile path\to\file.py
```

## Required Pre-Commit Checks

Before committing changes that touched Python/TS files containing Chinese text:

```powershell
python -m py_compile backend\app\api\kline.py backend\app\api\indices.py backend\app\jobs\daily_pipeline.py
uv run pytest tests/test_tushare_import_schema.py
pnpm build
git diff --check
```

If terminal output looks garbled, do not assume the file is corrupt. First verify with the UTF-8 diagnostics above.
