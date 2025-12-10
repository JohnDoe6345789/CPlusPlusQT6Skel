#pragma once

#include <map>
#include <string>
#include <vector>

// Minimal QML AST representation that is easy to traverse without pulling
// in a full QML runtime.
struct QmlNode {
    std::string type;
    std::string id;
    std::map<std::string, std::string> properties;
    std::vector<QmlNode> children;

    std::string property(const std::string &key, const std::string &defaultValue = "") const;
    const QmlNode *findChildByType(const std::string &wantedType) const;
    const QmlNode *findChildById(const std::string &wantedId) const;
};

class QmlDocument {
public:
    std::vector<QmlNode> roots;

    const QmlNode *firstRootOfType(const std::string &wantedType) const;
    const QmlNode *findById(const std::string &wantedId) const;
};

class QmlParser {
public:
    QmlDocument parseString(const std::string &source) const;
    QmlDocument parseFile(const std::string &path) const;
};
