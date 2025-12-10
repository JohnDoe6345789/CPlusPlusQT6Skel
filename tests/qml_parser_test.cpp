#include <QtTest>

#include "qml_parser.h"

class QmlParserTest : public QObject {
    Q_OBJECT

private slots:
    void parses_nested_items();
    void parses_inline_children();
};

void QmlParserTest::parses_nested_items() {
    const std::string qml = R"(
ApplicationWindow {
    id: root
    width: 320
    height: 200

    Column {
        spacing: 2
        Text {
            id: message
            text: "Hello"
        }
        Button {
            id: okButton
            text: "OK"
        }
    }
}
)";

    QmlParser parser;
    QmlDocument doc = parser.parseString(qml);

    QCOMPARE(doc.roots.size(), static_cast<size_t>(1));
    const QmlNode &root = doc.roots.front();
    QCOMPARE(root.type, std::string("ApplicationWindow"));
    QCOMPARE(root.id, std::string("root"));
    QCOMPARE(root.property("width"), std::string("320"));
    QCOMPARE(root.property("height"), std::string("200"));

    const QmlNode *column = root.findChildByType("Column");
    QVERIFY(column);
    QCOMPARE(column->property("spacing"), std::string("2"));

    const QmlNode *message = column->findChildById("message");
    QVERIFY(message);
    QCOMPARE(message->property("text"), std::string("Hello"));

    const QmlNode *okButton = column->findChildById("okButton");
    QVERIFY(okButton);
    QCOMPARE(okButton->property("text"), std::string("OK"));
}

void QmlParserTest::parses_inline_children() {
    const std::string qml = R"(
ApplicationWindow {
    Column {
        Text { id: inlineText; text: "Inline" }
        Label { text: "Secondary" }
        Button { text: "Run" }
    }
}
)";

    QmlParser parser;
    QmlDocument doc = parser.parseString(qml);

    const QmlNode *column = doc.firstRootOfType("Column");
    QVERIFY(column);
    QCOMPARE(column->children.size(), static_cast<size_t>(3));

    const QmlNode *inlineText = column->findChildById("inlineText");
    QVERIFY(inlineText);
    QCOMPARE(inlineText->property("text"), std::string("Inline"));

    const QmlNode *runButton = column->findChildByType("Button");
    QVERIFY(runButton);
    QCOMPARE(runButton->property("text"), std::string("Run"));
}

QTEST_GUILESS_MAIN(QmlParserTest)
#include "qml_parser_test.moc"
