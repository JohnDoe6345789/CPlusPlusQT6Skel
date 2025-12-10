#include <QtTest>

#include "qml_curses_frontend.h"

namespace {

struct DrawCall {
    int row = 0;
    int col = 0;
    std::string text;
};

class MockScreen : public ICursesScreen {
public:
    MockScreen(int rows, int cols) : rows_(rows), cols_(cols) {}

    void clear() override {
        cleared = true;
        draws.clear();
    }

    void drawText(int row, int col, const std::string &text) override {
        draws.push_back(DrawCall{row, col, text});
    }

    void refresh() override { refreshed = true; }

    int rows() const override { return rows_; }
    int cols() const override { return cols_; }

    bool cleared = false;
    bool refreshed = false;
    std::vector<DrawCall> draws;

private:
    int rows_;
    int cols_;
};

}  // namespace

class QmlCursesFrontendTest : public QObject {
    Q_OBJECT

private slots:
    void centers_title_and_items();
    void resolves_bindings();
};

void QmlCursesFrontendTest::centers_title_and_items() {
    const std::string qml = R"(
ApplicationWindow {
    title: "Demo"
    Column {
        spacing: 1
        Text { text: "Hello" }
        Button { text: "Do it" }
        Label { text: "Done" }
    }
}
)";

    QmlParser parser;
    auto doc = parser.parseString(qml);

    MockScreen screen(20, 40);
    QmlCursesFrontend frontend(screen);
    frontend.render(doc);

    QCOMPARE(screen.cleared, true);
    QCOMPARE(screen.refreshed, true);
    QCOMPARE(screen.draws.size(), static_cast<size_t>(4));

    const DrawCall &title = screen.draws[0];
    QCOMPARE(title.text, std::string("Demo"));
    QCOMPARE(title.row, 0);
    QCOMPARE(title.col, 18);  // (40 - 4) / 2

    const DrawCall &first = screen.draws[1];
    const DrawCall &second = screen.draws[2];
    const DrawCall &third = screen.draws[3];

    QCOMPARE(first.row, 2);
    QCOMPARE(second.row, 4);
    QCOMPARE(third.row, 6);

    QCOMPARE(first.text, std::string("Hello"));
    QCOMPARE(second.text, std::string("[ Do it ]"));
    QCOMPARE(third.text, std::string("Done"));

    QCOMPARE(second.col, 15);          // Widest item
    QCOMPARE(first.col, second.col + 2);  // Centered within padded width
    QCOMPARE(third.col, first.col);
}

void QmlCursesFrontendTest::resolves_bindings() {
    const std::string qml = R"(
ApplicationWindow {
    title: "Bindings"
    Column {
        spacing: 0
        Text { text: greeter.message }
        TextField { placeholderText: "name" }
        Button { text: actionLabel }
    }
}
)";

    QmlParser parser;
    auto doc = parser.parseString(qml);

    auto resolver = [](const std::string &binding) -> std::string {
        if (binding == "greeter.message") {
            return "Hello terminal";
        }
        if (binding == "actionLabel") {
            return "Run";
        }
        return binding;
    };

    MockScreen screen(25, 60);
    QmlCursesFrontend frontend(screen, resolver);
    frontend.render(doc);

    QCOMPARE(screen.draws.size(), static_cast<size_t>(4));
    QCOMPARE(screen.draws[0].text, std::string("Bindings"));
    QCOMPARE(screen.draws[1].text, std::string("Hello terminal"));
    QCOMPARE(screen.draws[2].text, std::string("[ name ]"));
    QCOMPARE(screen.draws[3].text, std::string("[ Run ]"));

    QCOMPARE(screen.draws[1].col, 23);  // (60 - 14) / 2
    QCOMPARE(screen.draws[2].col, 26);  // offset inside padded width
    QCOMPARE(screen.draws[3].col, 26);

    QCOMPARE(screen.draws[1].row, 2);
    QCOMPARE(screen.draws[2].row, 3);
    QCOMPARE(screen.draws[3].row, 4);
}

QTEST_GUILESS_MAIN(QmlCursesFrontendTest)
#include "qml_curses_frontend_test.moc"
