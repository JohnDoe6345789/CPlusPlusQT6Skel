#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "greeter.h"

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);

    QQmlApplicationEngine engine;
    Greeter greeter;
    engine.rootContext()->setContextProperty("greeter", &greeter);

    const QUrl mainUrl(QStringLiteral("qrc:/qml/Main.qml"));
    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreated,
        &app,
        [mainUrl](QObject *obj, const QUrl &objUrl) {
            if (!obj && objUrl == mainUrl) {
                QCoreApplication::exit(-1);
            }
        },
        Qt::QueuedConnection);

    engine.load(mainUrl);
    if (engine.rootObjects().isEmpty()) {
        return -1;
    }

    return app.exec();
}
