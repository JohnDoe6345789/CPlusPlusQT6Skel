#pragma once

#include <QObject>
#include <QString>

class Greeter : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString message READ message CONSTANT)

public:
    explicit Greeter(QObject *parent = nullptr);

    QString message() const;
    Q_INVOKABLE QString greet(const QString &name) const;
};
