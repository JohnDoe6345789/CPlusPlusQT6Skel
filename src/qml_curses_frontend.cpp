#include "qml_curses_frontend.h"

#include <algorithm>
#include <cctype>
#include <curses.h>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {

int parseIntOr(const std::string &text, int fallback) {
    try {
        size_t consumed = 0;
        const int value = std::stoi(text, &consumed);
        if (consumed == text.size()) {
            return value;
        }
    } catch (const std::exception &) {
        // Fall through to fallback.
    }
    return fallback;
}

}  // namespace

PdcursesScreen::PdcursesScreen(void *window) : window_(window ? window : stdscr) {}

void PdcursesScreen::clear() {
    if (!window_) {
        return;
    }
    werase(static_cast<WINDOW *>(window_));
}

void PdcursesScreen::drawText(int row, int col, const std::string &text) {
    if (!window_) {
        return;
    }
    mvwaddnstr(static_cast<WINDOW *>(window_), row, col, text.c_str(), static_cast<int>(text.size()));
}

void PdcursesScreen::refresh() {
    if (!window_) {
        return;
    }
    wrefresh(static_cast<WINDOW *>(window_));
}

int PdcursesScreen::rows() const {
    if (!window_) {
        return 0;
    }
    int y = 0;
    int x = 0;
    getmaxyx(static_cast<WINDOW *>(window_), y, x);
    return y;
}

int PdcursesScreen::cols() const {
    if (!window_) {
        return 0;
    }
    int y = 0;
    int x = 0;
    getmaxyx(static_cast<WINDOW *>(window_), y, x);
    return x;
}

QmlCursesFrontend::QmlCursesFrontend(ICursesScreen &screen, BindingResolver resolver)
    : screen_(screen), resolver_(std::move(resolver)) {}

std::string QmlCursesFrontend::resolveValue(const std::string &value) const {
    if (resolver_) {
        const std::string resolved = resolver_(value);
        if (!resolved.empty()) {
            return resolved;
        }
    }
    return value;
}

void QmlCursesFrontend::drawCentered(int row, const std::string &text, int paddedWidth) {
    if (text.empty()) {
        return;
    }

    const int length = static_cast<int>(text.size());
    const int width = paddedWidth > 0 ? paddedWidth : length;
    const int leftPadding = std::max(0, (screen_.cols() - width) / 2);
    const int offset = std::max(0, (width - length) / 2);
    screen_.drawText(row, leftPadding + offset, text);
}

void QmlCursesFrontend::render(const QmlDocument &document) {
    screen_.clear();

    const QmlNode *window = document.firstRootOfType("ApplicationWindow");
    if (!window) {
        screen_.refresh();
        return;
    }

    const std::string title = resolveValue(window->property("title"));
    int row = 0;
    if (!title.empty()) {
        drawCentered(row, title);
        row += 2;
    }

    const QmlNode *column = window->findChildByType("Column");
    if (!column) {
        screen_.refresh();
        return;
    }

    const int spacing = parseIntOr(column->property("spacing", "1"), 1);
    std::vector<std::string> lines;
    lines.reserve(column->children.size());

    for (const auto &child : column->children) {
        if (child.type == "Text" || child.type == "Label") {
            lines.push_back(resolveValue(child.property("text")));
        } else if (child.type == "TextField") {
            std::string content = resolveValue(child.property("text"));
            if (content.empty()) {
                content = resolveValue(child.property("placeholderText"));
            }
            if (content.empty()) {
                content = " ";
            }
            lines.push_back("[ " + content + " ]");
        } else if (child.type == "Button") {
            std::string label = child.property("text", "Button");
            label = resolveValue(label);
            lines.push_back("[ " + label + " ]");
        }
    }

    const int paddedWidth = lines.empty()
                                ? 0
                                : static_cast<int>(
                                      std::max_element(lines.begin(), lines.end(), [](const std::string &a, const std::string &b) {
                                          return a.size() < b.size();
                                      })
                                          ->size());

    for (const auto &line : lines) {
        if (row >= screen_.rows()) {
            break;
        }
        drawCentered(row, line, paddedWidth);
        row += 1 + spacing;
    }

    screen_.refresh();
}
