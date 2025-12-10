#include <QCoreApplication>
#include <algorithm>
#include <curses.h>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

#include "greeter.h"
#include "qml_curses_frontend.h"
#include "qml_parser.h"

namespace {

std::string resolveBinding(const Greeter &greeter, const std::string &binding) {
    if (binding == "greeter.message") {
        return greeter.message().toStdString();
    }
    if (binding == "greeter.greet" || binding == "greeter.greet()") {
        return greeter.greet("").toStdString();
    }
    return binding;
}

std::string defaultQmlPath(const std::filesystem::path &exeDir) {
    // Try a sibling "qml" folder first (matches source layout).
    const std::filesystem::path repoPath = exeDir / "qml" / "Main.qml";
    if (std::filesystem::exists(repoPath)) {
        return repoPath.string();
    }

    // Fallback to CMake build tree next to the binary.
    const std::filesystem::path buildPath = exeDir / ".." / "qml" / "Main.qml";
    if (std::filesystem::exists(buildPath)) {
        return std::filesystem::weakly_canonical(buildPath).string();
    }

    return "qml/Main.qml";
}

}  // namespace

int main(int argc, char *argv[]) {
    QCoreApplication app(argc, argv);

    const std::filesystem::path exeDir = std::filesystem::path(app.applicationDirPath().toStdWString());
    const std::string qmlPath = (argc > 1) ? argv[1] : defaultQmlPath(exeDir);

    QmlParser parser;
    QmlDocument document;
    try {
        document = parser.parseFile(qmlPath);
    } catch (const std::exception &ex) {
        std::cerr << "Failed to load " << qmlPath << ": " << ex.what() << std::endl;
        return 1;
    }

    if (initscr() == nullptr) {
        std::cerr << "Could not initialize curses screen." << std::endl;
        return 1;
    }
    cbreak();
    noecho();
    keypad(stdscr, TRUE);

    Greeter greeter;
    PdcursesScreen screen;  // defaults to stdscr
    QmlCursesFrontend frontend(screen, [&greeter](const std::string &binding) {
        return resolveBinding(greeter, binding);
    });
    frontend.render(document);

    const int instructionRow = std::max(0, screen.rows() - 1);
    mvprintw(instructionRow, 1, "Press any key to exit");
    refresh();
    getch();
    endwin();

    return 0;
}
