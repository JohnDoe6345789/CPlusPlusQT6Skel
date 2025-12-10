# CPlusPlusQT6Skel
Hello World Skel files for C++ QT6

## Downloading Qt

Use `download_qt6.py` to fetch prebuilt Qt 6 binaries (and optionally source) into the repo so builds work offline.

### Quick start (Windows desktop, auto-detect)
```sh
python download_qt6.py
```
Automatically selects your newest installed Visual Studio toolset (preferring VS 2022) and the latest Qt 6 release, then downloads it to `third_party/qt6` with common GUI modules.

### Customizing
- Pick version/arch/output (overrides auto-detection):  
  `python download_qt6.py --qt-version 6.6.3 --compiler win64_msvc2022_64 --output-dir vendor/qt6`
- Minimal modules:  
  `python download_qt6.py --modules qtbase qtdeclarative`
- Include build tools (ninja + CMake):  
  `python download_qt6.py --with-tools`
- Add Qt source (for IDE navigation):  
  `python download_qt6.py --with-src`  
  Limit source bundles: `--src-archives qtbase qtdeclarative`
- Preview only (no downloads):  
  `python download_qt6.py --dry-run`

Default output layout (example):
```
third_party/qt6/
  6.7.2/desktop/...
  6.7.2/Src/...   # only if --with-src
```
