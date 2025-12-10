#pragma once

#include <functional>
#include <memory>
#include <string>

#include "qml_parser.h"

class ICursesScreen {
public:
    virtual ~ICursesScreen() = default;

    virtual void clear() = 0;
    virtual void drawText(int row, int col, const std::string &text) = 0;
    virtual void refresh() = 0;
    virtual int rows() const = 0;
    virtual int cols() const = 0;
};

// Thin adapter over a PDCursesMod WINDOW*.
class PdcursesScreen : public ICursesScreen {
public:
    explicit PdcursesScreen(void *window = nullptr);

    void clear() override;
    void drawText(int row, int col, const std::string &text) override;
    void refresh() override;
    int rows() const override;
    int cols() const override;

private:
    void *window_;
};

using BindingResolver = std::function<std::string(const std::string &binding)>;

class QmlCursesFrontend {
public:
    QmlCursesFrontend(ICursesScreen &screen, BindingResolver resolver = nullptr);

    void render(const QmlDocument &document);

private:
    ICursesScreen &screen_;
    BindingResolver resolver_;

    std::string resolveValue(const std::string &value) const;
    void drawCentered(int row, const std::string &text, int paddedWidth = -1);
};
