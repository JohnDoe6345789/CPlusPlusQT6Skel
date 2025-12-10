#include <QtTest>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickWindow>

#include "greeter.h"

class MainQmlTest : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();
    void default_label_matches_greeter();
    void clicking_button_updates_output();

private:
    QQmlApplicationEngine engine_;
    QQuickWindow *window_ = nullptr;
    Greeter greeter_;
};

void MainQmlTest::initTestCase() {
    engine_.rootContext()->setContextProperty("greeter", &greeter_);
    engine_.load(QUrl(QStringLiteral("qrc:/qml/Main.qml")));

    const auto roots = engine_.rootObjects();
    QVERIFY(!roots.isEmpty());

    window_ = qobject_cast<QQuickWindow *>(roots.first());
    QVERIFY(window_);

    window_->show();
    QVERIFY(QTest::qWaitForWindowActive(window_));
}

void MainQmlTest::cleanupTestCase() {
    window_ = nullptr;
    engine_.clearComponentCache();
}

void MainQmlTest::default_label_matches_greeter() {
    auto greetingText = window_->findChild<QObject *>("greetingText");
    QVERIFY(greetingText);
    QCOMPARE(greetingText->property("text").toString(), greeter_.message());
}

void MainQmlTest::clicking_button_updates_output() {
    auto nameField = window_->findChild<QObject *>("nameField");
    auto helloButton = window_->findChild<QObject *>("helloButton");
    auto outputLabel = window_->findChild<QObject *>("outputLabel");

    QVERIFY(nameField);
    QVERIFY(helloButton);
    QVERIFY(outputLabel);

    nameField->setProperty("text", QStringLiteral("Ada"));

    const bool invoked = QMetaObject::invokeMethod(helloButton, "click");
    QVERIFY(invoked);

    QTRY_COMPARE(outputLabel->property("text").toString(), QStringLiteral("Hello, Ada!"));
}

QTEST_MAIN(MainQmlTest)
#include "main_qml_test.moc"
