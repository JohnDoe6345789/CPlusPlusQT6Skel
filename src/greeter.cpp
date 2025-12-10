#include "greeter.h"

Greeter::Greeter(QObject *parent) : QObject(parent) {}

QString Greeter::message() const {
    return QStringLiteral("Hello from C++");
}

QString Greeter::greet(const QString &name) const {
    const QString trimmed = name.trimmed();
    if (trimmed.isEmpty()) {
        return QStringLiteral("Hello, Qt 6!");
    }
    return QStringLiteral("Hello, %1!").arg(trimmed);
}
