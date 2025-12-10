#include "qml_parser.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace {

std::string ltrim(const std::string &text) {
    const auto it = std::find_if_not(text.begin(), text.end(), [](unsigned char ch) {
        return std::isspace(ch) != 0;
    });
    return std::string(it, text.end());
}

std::string rtrim(const std::string &text) {
    const auto it = std::find_if_not(text.rbegin(), text.rend(), [](unsigned char ch) {
        return std::isspace(ch) != 0;
    });
    return std::string(text.begin(), it.base());
}

std::string trim(const std::string &text) {
    return rtrim(ltrim(text));
}

std::string stripQuotes(const std::string &value) {
    if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
        return value.substr(1, value.size() - 2);
    }
    return value;
}

void parseInlineProperties(const std::string &propertiesText, QmlNode &node) {
    std::stringstream stream(propertiesText);
    std::string segment;

    while (std::getline(stream, segment, ';')) {
        const auto trimmed = trim(segment);
        if (trimmed.empty()) {
            continue;
        }

        const auto colonPos = trimmed.find(':');
        if (colonPos == std::string::npos) {
            continue;
        }

        const std::string key = trim(trimmed.substr(0, colonPos));
        const std::string rawValue = trim(trimmed.substr(colonPos + 1));
        const std::string value = stripQuotes(rawValue);

        node.properties[key] = value;
        if (key == "id") {
            node.id = value;
        }
    }
}

}  // namespace

std::string QmlNode::property(const std::string &key, const std::string &defaultValue) const {
    const auto it = properties.find(key);
    if (it == properties.end()) {
        return defaultValue;
    }
    return it->second;
}

const QmlNode *QmlNode::findChildByType(const std::string &wantedType) const {
    for (const auto &child : children) {
        if (child.type == wantedType) {
            return &child;
        }
        if (const auto *nested = child.findChildByType(wantedType)) {
            return nested;
        }
    }
    return nullptr;
}

const QmlNode *QmlNode::findChildById(const std::string &wantedId) const {
    for (const auto &child : children) {
        if (child.id == wantedId) {
            return &child;
        }
        if (const auto *nested = child.findChildById(wantedId)) {
            return nested;
        }
    }
    return nullptr;
}

const QmlNode *QmlDocument::firstRootOfType(const std::string &wantedType) const {
    for (const auto &root : roots) {
        if (root.type == wantedType) {
            return &root;
        }
        if (const auto *nested = root.findChildByType(wantedType)) {
            return nested;
        }
    }
    return nullptr;
}

const QmlNode *QmlDocument::findById(const std::string &wantedId) const {
    for (const auto &root : roots) {
        if (root.id == wantedId) {
            return &root;
        }
        if (const auto *nested = root.findChildById(wantedId)) {
            return nested;
        }
    }
    return nullptr;
}

QmlDocument QmlParser::parseFile(const std::string &path) const {
    std::ifstream file(path);
    if (!file) {
        throw std::runtime_error("Failed to open QML file: " + path);
    }

    std::ostringstream buffer;
    buffer << file.rdbuf();
    return parseString(buffer.str());
}

QmlDocument QmlParser::parseString(const std::string &source) const {
    QmlDocument document;
    std::vector<QmlNode *> stack;

    auto pushNode = [&](const std::string &type) -> QmlNode & {
        if (stack.empty()) {
            document.roots.push_back(QmlNode{});
            stack.push_back(&document.roots.back());
        } else {
            stack.back()->children.push_back(QmlNode{});
            stack.push_back(&stack.back()->children.back());
        }
        stack.back()->type = type;
        return *stack.back();
    };

    std::istringstream input(source);
    std::string line;
    while (std::getline(input, line)) {
        std::string trimmed = trim(line);
        if (trimmed.empty() || trimmed.rfind("//", 0) == 0) {
            continue;
        }

        // Handle inline opening brace.
        const auto bracePos = trimmed.find('{');
        if (bracePos != std::string::npos) {
            const std::string type = trim(trimmed.substr(0, bracePos));
            if (type.empty()) {
                continue;
            }

            QmlNode &node = pushNode(type);
            std::string remainder = trim(trimmed.substr(bracePos + 1));
            bool closesInline = false;
            if (!remainder.empty() && remainder.back() == '}') {
                closesInline = true;
                remainder = trim(remainder.substr(0, remainder.size() - 1));
            }

            if (!remainder.empty()) {
                parseInlineProperties(remainder, node);
            }

            if (closesInline && !stack.empty()) {
                stack.pop_back();
            }
            continue;
        }

        if (trimmed == "}") {
            if (!stack.empty()) {
                stack.pop_back();
            }
            continue;
        }

        const auto colonPos = trimmed.find(':');
        if (colonPos == std::string::npos || stack.empty()) {
            continue;
        }

        const std::string key = trim(trimmed.substr(0, colonPos));
        std::string rawValue = trim(trimmed.substr(colonPos + 1));
        bool closesScope = false;
        if (!rawValue.empty() && rawValue.back() == '}') {
            closesScope = true;
            rawValue = trim(rawValue.substr(0, rawValue.size() - 1));
        }

        const std::string value = stripQuotes(rawValue);
        stack.back()->properties[key] = value;
        if (key == "id") {
            stack.back()->id = value;
        }

        if (closesScope && !stack.empty()) {
            stack.pop_back();
        }
    }

    return document;
}
