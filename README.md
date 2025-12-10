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

## Sample Qt Quick app + tests

This repo now contains a minimal Qt 6 + QML app (`sample_app`) plus a small test suite.

### Configure and build (Windows, Ninja + MSVC example)
```sh
cmake -B build -G "Ninja" ^
  -DCMAKE_PREFIX_PATH=%CD%\third_party\qt6\6.10.1\msvc2022_64
cmake --build build
```

### Run the app
```sh
build\sample_app.exe
```

### Run tests
```sh
ctest --test-dir build
```

## PDCursesMod (WinCon)

The WinCon flavor of [PDCursesMod](https://github.com/Bill-Gray/PDCursesMod) v4.5.3 is vendored in `third_party/PDCursesMod` and exposed via the CMake target `PDCursesMod::pdcurses`. It is built as a static library with only the WinCon backend (no SDL/OpenGL extras) when `BUILD_PDCURSES_WINCON` is ON (default on Windows).

Link it to your target, for example:
```cmake
target_link_libraries(your_target PRIVATE PDCursesMod::pdcurses)
```

## QML to PDCurses prototype

`qml_curses` provides a tiny QML parser plus a PDCursesMod renderer for column-based layouts. It understands basic `ApplicationWindow` + `Column` trees with `Text`, `TextField`, `Label`, and `Button` children and centers them in the console. The target is only built when the vendored `PDCursesMod::pdcurses` library is available.

Example usage:
```cpp
#include "qml_curses_frontend.h"
#include "qml_parser.h"
#include <curses.h>

int main() {
    initscr();
    noecho();

    QmlParser parser;
    QmlDocument doc = parser.parseFile("qml/Main.qml");

    PdcursesScreen screen;  // wraps stdscr
    QmlCursesFrontend frontend(screen, [](const std::string &binding) {
        if (binding == "greeter.message") return std::string("Hello from C++");
        return binding;
    });
    frontend.render(doc);

    getch();
    endwin();
    return 0;
}
```

The `qml_curses_tests` target exercises the parser and renderer without requiring a live console by mocking the curses screen.
