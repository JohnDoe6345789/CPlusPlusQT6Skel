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

## Cross-platform build helper

`dev_tool.py` wraps common CMake actions for Windows, macOS, and Linux. It auto-picks Ninja if present (otherwise defers to CMake's default), reconfigures on each call, and tries to find Qt under `third_party/qt6` (or honors `QT_PREFIX_PATH` / `--qt-prefix`).

User defaults (build dir/type, Qt prefix, generator, run targets, Qt download location) are stored in a JSON settings file under XDG config (`~/.config/CPlusPlusQT6Skel/settings.json`) or `%APPDATA%\CPlusPlusQT6Skel\settings.json` on Windows. Manage them with `python dev_tool.py settings`.

```sh
# Verify environment (compiler, cmake, generator, Qt) and get guidance to fix it
python dev_tool.py verify

# Build everything into ./build (Debug by default)
python dev_tool.py build

# Build and run the console renderer (skips rebuild on request; omit target to choose from detected targets)
python dev_tool.py run sample_cli --skip-build -- --help

# Build and run the test suite (passes args to ctest)
python dev_tool.py test -- -V

# Check for newer Qt / PDCursesMod releases upstream
python dev_tool.py check-updates

# Configure defaults (build dir, Qt prefix, generator, run targets)
python dev_tool.py settings --print        # show current values and config path
python dev_tool.py settings --set build_dir=C:/dev/qt-build

# Verify environment (compiler, cmake, generator, Qt) and get guidance to fix it
python dev_tool.py verify

# Interactive menu to build / test / run (default if no args and in a TTY)
python dev_tool.py menu
# or simply:
python dev_tool.py

When running without a target, the tool tries to list runnable CMake targets from the current build directory (Ninja targets or `cmake --build --target help`) and falls back to the sample app/CLI defaults.
```

## Sample Qt Quick app + tests

This repo now contains a minimal Qt 6 + QML app (`sample_app`) plus a small test suite.

### Configure and build (Windows, Ninja + MSVC example)
```sh
cmake -B build -G "Ninja" ^
  -DCMAKE_PREFIX_PATH=%CD%\third_party\qt6\6.10.1\msvc2022_64
cmake --build build
```

### Run the GUI app
```sh
build\sample_app.exe
```

### Run the terminal CLI (Win/macOS/Linux)
`sample_cli` renders the same `qml/Main.qml` layout into the console using curses.

- Windows: builds against the bundled WinCon PDCursesMod (`third_party/PDCursesMod`).
- macOS/Linux: uses the system curses/ncurses development package (install it first if your distro omits it).

```sh
# From the build directory produced above:
./sample_cli             # uses ../qml/Main.qml by default
./sample_cli path/to/Main.qml  # optional explicit QML path
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
