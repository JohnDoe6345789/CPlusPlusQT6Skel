#include <QtTest>

#include "greeter.h"

class GreeterTest : public QObject {
    Q_OBJECT

private slots:
    void message_is_constant();
    void greet_formats_name();
    void greet_handles_empty_input();
};

void GreeterTest::message_is_constant() {
    Greeter greeter;
    QCOMPARE(greeter.message(), QStringLiteral("Hello from C++"));
}

void GreeterTest::greet_formats_name() {
    Greeter greeter;
    QCOMPARE(greeter.greet(QStringLiteral("Qt Dev")), QStringLiteral("Hello, Qt Dev!"));
    QCOMPARE(greeter.greet(QStringLiteral("  Sam  ")), QStringLiteral("Hello, Sam!"));
}

void GreeterTest::greet_handles_empty_input() {
    Greeter greeter;
    QCOMPARE(greeter.greet(QString()), QStringLiteral("Hello, Qt 6!"));
    QCOMPARE(greeter.greet(QStringLiteral("   ")), QStringLiteral("Hello, Qt 6!"));
}

QTEST_GUILESS_MAIN(GreeterTest)
#include "greeter_test.moc"
